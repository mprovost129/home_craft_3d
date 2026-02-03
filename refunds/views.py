# refunds/views.py
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.throttle import ThrottleRule, throttle
from orders.models import Order, OrderItem
from products.permissions import is_owner_user, is_seller_user

from .forms import RefundRequestCreateForm, SellerDecisionForm
from .models import RefundRequest
from .services import create_refund_request, seller_decide, trigger_refund

logger = logging.getLogger(__name__)


# ----------------------------
# Throttle rules (tune anytime)
# ----------------------------
REFUND_CREATE_RULE = ThrottleRule(key_prefix="refund_create", limit=3, window_seconds=60)
REFUND_SELLER_DECIDE_RULE = ThrottleRule(key_prefix="refund_seller_decide", limit=10, window_seconds=60)
REFUND_TRIGGER_RULE = ThrottleRule(key_prefix="refund_trigger", limit=3, window_seconds=60)
REFUND_STAFF_TRIGGER_RULE = ThrottleRule(key_prefix="refund_staff_trigger", limit=10, window_seconds=60)


# ============================================================
# Helpers
# ============================================================
def _token_from_request(request: HttpRequest) -> str:
    return (request.GET.get("t") or "").strip()


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _user_can_access_order(request: HttpRequest, order: Order) -> bool:
    """
    Mirrors orders.views enforcement:
    - staff/superuser always allowed
    - buyer can access their own order
    - guest can access via token ?t=<order.order_token>
    """
    if request.user.is_authenticated and _is_staff(request.user):
        return True

    if getattr(order, "buyer_id", None):
        return request.user.is_authenticated and request.user.id == order.buyer_id

    t = _token_from_request(request)
    return bool(t) and str(t) == str(getattr(order, "order_token", ""))


def _require_seller_or_staff(request: HttpRequest, rr: RefundRequest) -> None:
    """
    Only:
    - rr.seller
    - owner
    - staff
    can act on seller-side refund request.
    """
    user = request.user
    if not user.is_authenticated:
        raise Http404("Not found")

    if is_owner_user(user) or _is_staff(user):
        return

    if rr.seller_id != user.id:
        raise Http404("Not found")


def _redirect_order_detail(order: Order, token: str = "") -> str:
    """
    Token-preserving redirect for guest orders.
    """
    if getattr(order, "buyer_id", None):
        return reverse("orders:detail", kwargs={"order_id": order.pk})

    token = (token or "").strip()
    if token:
        return f"{reverse('orders:detail', kwargs={'order_id': order.pk})}?t={token}"
    return reverse("orders:detail", kwargs={"order_id": order.pk})


def _order_token_for_redirect(request: HttpRequest, order: Order) -> str:
    """
    When acting on a guest order, preserve its token in redirects.
    """
    if getattr(order, "buyer_id", None):
        return ""
    return _token_from_request(request)


# ============================================================
# Buyer / Guest
# ============================================================
@login_required
def buyer_list(request: HttpRequest) -> HttpResponse:
    qs = RefundRequest.objects.filter(buyer=request.user).select_related("order", "order_item", "seller")
    return render(request, "refunds/buyer_list.html", {"refunds": qs})


@login_required
def buyer_detail(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(
        RefundRequest.objects.select_related("order", "order_item", "seller", "buyer"),
        pk=refund_id,
    )
    if rr.buyer_id != request.user.id and not _is_staff(request.user):
        raise Http404("Not found")
    return render(request, "refunds/buyer_detail.html", {"rr": rr})


@throttle(REFUND_CREATE_RULE)
def buyer_create(request: HttpRequest, order_id, item_id) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    item = get_object_or_404(OrderItem.objects.select_related("order", "product"), pk=item_id, order=order)

    # Access control: buyer OR guest token
    if not _user_can_access_order(request, order):
        raise Http404("Not found")

    if request.method == "POST":
        form = RefundRequestCreateForm(request.POST)
        if form.is_valid():
            try:
                create_refund_request(
                    order=order,
                    item=item,
                    requester_user=request.user if request.user.is_authenticated else None,
                    requester_email=form.cleaned_data.get("guest_email", "") or "",
                    reason=form.cleaned_data["reason"],
                    notes=form.cleaned_data.get("notes", "") or "",
                    token=_token_from_request(request),
                )
                messages.success(request, "Refund request submitted.")
                return redirect(_redirect_order_detail(order, _order_token_for_redirect(request, order)))
            except (PermissionDenied, ValidationError) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, str(e) or "Unable to submit refund request.")
    else:
        form = RefundRequestCreateForm()

    return render(
        request,
        "refunds/buyer_create.html",
        {"order": order, "item": item, "form": form, "token": _token_from_request(request)},
    )


# ============================================================
# Seller
# ============================================================
@login_required
def seller_queue(request: HttpRequest) -> HttpResponse:
    if not (is_seller_user(request.user) or is_owner_user(request.user) or _is_staff(request.user)):
        raise Http404("Not found")

    qs = RefundRequest.objects.select_related("order", "order_item", "seller", "buyer").filter(
        seller=request.user
    )
    return render(request, "refunds/seller_queue.html", {"refunds": qs})


@login_required
def seller_detail(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(
        RefundRequest.objects.select_related("order", "order_item", "seller", "buyer"),
        pk=refund_id,
    )
    _require_seller_or_staff(request, rr)

    decision_form = SellerDecisionForm()
    return render(request, "refunds/seller_detail.html", {"rr": rr, "decision_form": decision_form})


@login_required
@require_POST
@throttle(REFUND_SELLER_DECIDE_RULE)
def seller_approve(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(RefundRequest.objects.select_related("order"), pk=refund_id)
    _require_seller_or_staff(request, rr)

    form = SellerDecisionForm(request.POST)
    if form.is_valid():
        try:
            seller_decide(rr=rr, actor_user=request.user, approve=True, note=form.cleaned_data.get("decision_note", ""))
            messages.success(request, "Refund request approved.")
        except Exception as e:
            messages.error(request, str(e) or "Unable to approve refund request.")
    else:
        messages.error(request, "Please correct the form.")
    return redirect("orders:refunds:seller_detail", refund_id=rr.pk)


@login_required
@require_POST
@throttle(REFUND_SELLER_DECIDE_RULE)
def seller_decline(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(RefundRequest.objects.select_related("order"), pk=refund_id)
    _require_seller_or_staff(request, rr)

    form = SellerDecisionForm(request.POST)
    if form.is_valid():
        try:
            seller_decide(rr=rr, actor_user=request.user, approve=False, note=form.cleaned_data.get("decision_note", ""))
            messages.success(request, "Refund request declined.")
        except Exception as e:
            messages.error(request, str(e) or "Unable to decline refund request.")
    else:
        messages.error(request, "Please correct the form.")
    return redirect("orders:refunds:seller_detail", refund_id=rr.pk)


@login_required
@require_POST
@throttle(REFUND_TRIGGER_RULE)
def seller_trigger_refund(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(RefundRequest.objects.select_related("order"), pk=refund_id)
    _require_seller_or_staff(request, rr)

    try:
        trigger_refund(rr=rr, actor_user=request.user, allow_staff_safety_valve=False)
        messages.success(request, "Refund processed.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to process refund.")
    return redirect("orders:refunds:seller_detail", refund_id=rr.pk)


# ============================================================
# Staff safety valve
# ============================================================
@user_passes_test(_is_staff)
def staff_queue(request: HttpRequest) -> HttpResponse:
    qs = RefundRequest.objects.select_related("order", "order_item", "seller", "buyer").order_by("-created_at")[:500]
    return render(request, "refunds/staff_queue.html", {"refunds": qs})


@user_passes_test(_is_staff)
@require_POST
@throttle(REFUND_STAFF_TRIGGER_RULE)
def staff_trigger_refund(request: HttpRequest, refund_id) -> HttpResponse:
    rr = get_object_or_404(RefundRequest.objects.select_related("order"), pk=refund_id)
    try:
        trigger_refund(rr=rr, actor_user=request.user, allow_staff_safety_valve=True)
        messages.success(request, "Refund processed.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to process refund.")
    return redirect("orders:refunds:staff_queue")
