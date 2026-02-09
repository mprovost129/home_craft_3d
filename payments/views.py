# payments/views.py
from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from products.permissions import seller_required

from .models import SellerBalanceEntry, SellerStripeAccount
from .services import get_seller_balance_cents
from .stripe_connect import create_account_link, create_express_account, retrieve_account


def _seller_email_for_connect(user) -> str:
    """Pick a stable email for Stripe Connect.

    Preference order:
      1) user.email (if you have a custom user model with email)
      2) user.profile.email (your Profile model stores contact email)
    """
    email = (getattr(user, "email", "") or "").strip()
    if email:
        return email

    profile = getattr(user, "profile", None)
    if profile is not None:
        email = (getattr(profile, "email", "") or "").strip()
        if email:
            return email

    return ""


def _refresh_connect_status(obj: SellerStripeAccount) -> None:
    """Refresh Stripe Connect status fields from Stripe (best-effort)."""
    if not obj.stripe_account_id:
        return

    acct = retrieve_account(obj.stripe_account_id)
    obj.details_submitted = bool(acct.get("details_submitted"))
    obj.charges_enabled = bool(acct.get("charges_enabled"))
    obj.payouts_enabled = bool(acct.get("payouts_enabled"))
    obj.save(
        update_fields=[
            "details_submitted",
            "charges_enabled",
            "payouts_enabled",
            "updated_at",
        ]
    )

    # This will also sync Profile legacy fields now.
    obj.mark_onboarding_completed_if_ready()


@seller_required
def connect_status(request):
    """Seller-facing status page + CTA to start/continue Stripe onboarding."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    # Optional: light refresh on GET if linked but not ready yet.
    if obj.stripe_account_id and not obj.is_ready:
        try:
            _refresh_connect_status(obj)
        except Exception:
            pass

    context = {
        "stripe": obj,
        "ready": obj.is_ready,
    }
    return render(request, "payments/connect_status.html", context)


@seller_required
def connect_start(request):
    """Create Stripe Express account if needed, then redirect to onboarding link."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    if not obj.stripe_account_id:
        email = _seller_email_for_connect(request.user)
        if not email:
            messages.error(
                request,
                "Your account is missing an email. Add one in your profile, then try again.",
            )
            return redirect("payments:connect_status")

        acct = create_express_account(email=email, country="US")
        obj.stripe_account_id = acct["id"]
        obj.details_submitted = bool(acct.get("details_submitted"))
        obj.charges_enabled = bool(acct.get("charges_enabled"))
        obj.payouts_enabled = bool(acct.get("payouts_enabled"))
        obj.save(
            update_fields=[
                "stripe_account_id",
                "details_submitted",
                "charges_enabled",
                "payouts_enabled",
                "updated_at",
            ]
        )

        # Immediately mirror legacy Profile fields.
        obj.mark_onboarding_completed_if_ready()

    obj.mark_onboarding_started()

    link = create_account_link(stripe_account_id=obj.stripe_account_id)
    return redirect(link["url"])


@seller_required
@require_POST
def connect_sync(request):
    """Manual refresh button for sellers (handy if webhook delivery is delayed)."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)
    if not obj.stripe_account_id:
        messages.info(request, "You haven’t started Stripe onboarding yet.")
        return redirect("payments:connect_status")

    try:
        _refresh_connect_status(obj)
    except Exception:
        messages.info(
            request, "Couldn’t refresh Stripe status right now. Try again in a moment."
        )
        return redirect("payments:connect_status")

    if obj.is_ready:
        messages.success(request, "Stripe payouts are enabled. You’re ready to sell!")
    else:
        messages.info(
            request,
            "Stripe status refreshed. If anything is missing, click Continue to finish onboarding.",
        )

    return redirect("payments:connect_status")


@seller_required
def connect_refresh(request):
    """Stripe sends user here if they abandon or the session expires."""
    messages.info(
        request, "Your Stripe onboarding link expired. Click Continue to generate a new one."
    )
    return redirect("payments:connect_status")


@seller_required
def connect_return(request):
    """Stripe sends user here after onboarding. We refresh the account status."""
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    if obj.stripe_account_id:
        try:
            _refresh_connect_status(obj)
        except Exception:
            pass

    if obj.is_ready:
        messages.success(request, "Stripe payouts are enabled. You’re ready to sell!")
    else:
        messages.info(
            request,
            "Stripe setup saved. If anything is missing, click Continue to finish onboarding.",
        )

    return redirect("payments:connect_status")


@seller_required
def payouts_dashboard(request):
    """
    Seller payouts / ledger page.

    Shows:
      - current signed balance (platform owes seller if positive; seller owes platform if negative)
      - ledger entries (append-only)
      - optional filters: reason, q (note/order id)
    """
    seller = request.user

    balance_cents = int(get_seller_balance_cents(seller=seller) or 0)

    reason = (request.GET.get("reason") or "").strip()
    q = (request.GET.get("q") or "").strip()

    entries = SellerBalanceEntry.objects.filter(seller=seller).select_related(
        "order", "order_item"
    )

    if reason:
        entries = entries.filter(reason=reason)

    if q:
        entries = entries.filter(Q(note__icontains=q) | Q(order__id__icontains=q))

    entries = entries.order_by("-created_at")

    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    stripe_obj, _ = SellerStripeAccount.objects.get_or_create(user=seller)

    context = {
        "balance_cents": balance_cents,
        "page_obj": page,
        "entries": page.object_list,
        "reason": reason,
        "q": q,
        "reasons": SellerBalanceEntry.Reason.choices,
        "stripe": stripe_obj,
        "stripe_ready": stripe_obj.is_ready,
    }
    return render(request, "payments/payouts_dashboard.html", context)


def _verify_and_parse_connect_webhook(payload: bytes, sig_header: str):
    """Verify Stripe webhook for Connect events."""
    import stripe
    from django.conf import settings

    stripe.api_key = settings.STRIPE_SECRET_KEY

    secret = getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("STRIPE_CONNECT_WEBHOOK_SECRET is not configured")

    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=secret,
    )


@csrf_exempt
@require_POST
def stripe_connect_webhook(request):
    """Stripe webhook endpoint to keep Connect statuses updated."""
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return HttpResponseBadRequest("Missing signature")

    try:
        event = _verify_and_parse_connect_webhook(payload, sig_header)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "account.updated":
        acct_id = data_object.get("id", "")
        if acct_id:
            obj = SellerStripeAccount.objects.filter(stripe_account_id=acct_id).first()
            if obj:
                obj.details_submitted = bool(data_object.get("details_submitted"))
                obj.charges_enabled = bool(data_object.get("charges_enabled"))
                obj.payouts_enabled = bool(data_object.get("payouts_enabled"))
                obj.save(
                    update_fields=[
                        "details_submitted",
                        "charges_enabled",
                        "payouts_enabled",
                        "updated_at",
                    ]
                )
                # This now also syncs Profile legacy fields.
                obj.mark_onboarding_completed_if_ready()

    return HttpResponse(status=200)
