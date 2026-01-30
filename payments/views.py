from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from products.permissions import seller_required, is_owner_user
from .models import SellerStripeAccount
from .stripe_connect import create_account_link, create_express_account, retrieve_account
from orders.stripe_service import verify_and_parse_webhook  # reuse existing webhook verifier


@seller_required
def connect_status(request):
    """
    Seller-facing status page + CTA to start/continue Stripe onboarding.
    Owner/admin can view their own, but this page is meant for sellers.
    """
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    context = {
        "stripe": obj,
        "ready": obj.is_ready,
    }
    return render(request, "payments/connect_status.html", context)


@seller_required
@require_POST
def connect_start(request):
    """
    Creates Stripe Express account if needed, then redirects to onboarding link.
    """
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    # Create account if not linked yet
    if not obj.stripe_account_id:
        email = getattr(request.user, "email", "") or ""
        if not email:
            messages.error(request, "Your account is missing an email. Add one in your profile, then try again.")
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

    obj.mark_onboarding_started()

    link = create_account_link(stripe_account_id=obj.stripe_account_id)
    return redirect(link["url"])


@seller_required
def connect_refresh(request):
    """
    Stripe sends user here if they abandon or the session expires.
    """
    messages.info(request, "Your Stripe onboarding link expired. Click Continue to generate a new one.")
    return redirect("payments:connect_status")


@seller_required
def connect_return(request):
    """
    Stripe sends user here after onboarding. We refresh the account status.
    """
    obj, _ = SellerStripeAccount.objects.get_or_create(user=request.user)

    if obj.stripe_account_id:
        acct = retrieve_account(obj.stripe_account_id)
        obj.details_submitted = bool(acct.get("details_submitted"))
        obj.charges_enabled = bool(acct.get("charges_enabled"))
        obj.payouts_enabled = bool(acct.get("payouts_enabled"))
        obj.save(update_fields=["details_submitted", "charges_enabled", "payouts_enabled", "updated_at"])
        obj.mark_onboarding_completed_if_ready()

    if obj.is_ready:
        messages.success(request, "Stripe payouts are enabled. You’re ready to sell!")
    else:
        messages.info(request, "Stripe setup saved. If anything is missing, click Continue to finish onboarding.")

    return redirect("payments:connect_status")


@csrf_exempt
def stripe_connect_webhook(request):
    """
    Stripe webhook endpoint to keep Connect statuses updated.
    Configure Stripe to send at least:
      - account.updated
    """
    payload = request.body
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return HttpResponseBadRequest("Missing signature")

    try:
        event = verify_and_parse_webhook(payload, sig_header)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}

    # Keep seller linkage updated
    if event_type == "account.updated":
        acct_id = data_object.get("id", "")
        if acct_id:
            obj = SellerStripeAccount.objects.filter(stripe_account_id=acct_id).first()
            if obj:
                obj.details_submitted = bool(data_object.get("details_submitted"))
                obj.charges_enabled = bool(data_object.get("charges_enabled"))
                obj.payouts_enabled = bool(data_object.get("payouts_enabled"))
                obj.save(update_fields=["details_submitted", "charges_enabled", "payouts_enabled", "updated_at"])
                obj.mark_onboarding_completed_if_ready()

    return HttpResponse(status=200)
