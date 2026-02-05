# legal/views.py
from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import LegalDocument
from .services import get_latest_published_docs, record_acceptance


@dataclass(frozen=True)
class LegalDocFallback:
    title: str
    summary: str
    body: str
    version: int = 0


def _get_latest_or_fallback(doc_type: str):
    doc = (
        LegalDocument.objects.filter(doc_type=doc_type, is_published=True)
        .order_by("-version")
        .first()
    )
    if doc:
        return doc

    title_map = {
        LegalDocument.DocType.TERMS: "Terms of Service",
        LegalDocument.DocType.PRIVACY: "Privacy Policy",
        LegalDocument.DocType.REFUND: "Refund Policy",
        LegalDocument.DocType.CONTENT: "Content & Safety Policy",
    }

    body_map = {
        LegalDocument.DocType.TERMS: (
            "Welcome to Home Craft 3D. By using this site, you agree to these Terms.\n\n"
            "1) Marketplace role\n"
            "Home Craft 3D is a marketplace that connects buyers and independent sellers. Sellers are responsible for their listings, fulfillment, and compliance with laws.\n\n"
            "2) Accounts\n"
            "You’re responsible for your account activity, keeping your credentials secure, and providing accurate information.\n\n"
            "3) Listings & purchases\n"
            "Sellers set prices, descriptions, and file contents. Buyers should review listing details before purchase. Digital files are delivered electronically; physical items are shipped by sellers.\n\n"
            "4) Payments\n"
            "Payments are processed at checkout. Order status is “pending payment” until payment is confirmed.\n\n"
            "5) Digital items\n"
            "Digital downloads are intended for personal use unless the listing specifies otherwise. Sharing, reselling, or redistributing files without permission is prohibited.\n\n"
            "6) Shipping (physical items)\n"
            "Shipping timelines and handling are set by sellers. Delays may occur due to carrier issues or production time.\n\n"
            "7) Prohibited content\n"
            "Listings and user content must comply with our Content & Safety Policy.\n\n"
            "8) Refunds\n"
            "Refund eligibility is described in the Refund Policy.\n\n"
            "9) Intellectual property\n"
            "Sellers must own or have rights to sell their content. Buyers must respect seller IP rights.\n\n"
            "10) Limitation of liability\n"
            "Home Craft 3D is not liable for indirect damages, lost profits, or issues arising from seller listings or fulfillment.\n\n"
            "11) Changes\n"
            "We may update these Terms. Continued use of the site means you accept the updated Terms.\n\n"
            "Contact: homecraft3dstore@gmail.com"
        ),
        LegalDocument.DocType.PRIVACY: (
            "This Privacy Policy explains how we collect, use, and share information.\n\n"
            "1) Information we collect\n"
            "- Account details (email, username)\n"
            "- Order and payment details (processed securely by our payment providers)\n"
            "- Usage data (pages visited, actions taken)\n"
            "- Device and browser information\n\n"
            "2) How we use information\n"
            "- To process orders and deliver digital downloads\n"
            "- To provide customer support\n"
            "- To improve site performance and security\n"
            "- To comply with legal obligations\n\n"
            "3) Sharing\n"
            "We share only what’s necessary with sellers (to fulfill orders) and payment providers (to process payments). We do not sell personal data.\n\n"
            "4) Cookies\n"
            "We use cookies for login sessions, cart functionality, and analytics. You can manage cookies in your browser settings.\n\n"
            "5) Data retention\n"
            "We keep data as long as needed for orders, legal compliance, and support.\n\n"
            "6) Your rights\n"
            "You can request access, corrections, or deletion of your data by contacting support.\n\n"
            "Contact: homecraft3dstore@gmail.com"
        ),
        LegalDocument.DocType.REFUND: (
            "Refunds depend on item type.\n\n"
            "Digital files\n"
            "- Digital downloads are generally non-refundable once delivered.\n"
            "- Refunds may be granted if a file is corrupted or materially different from the listing.\n\n"
            "Physical items\n"
            "- Returns are accepted within 14 days of delivery if the item is defective or significantly not as described.\n"
            "- Buyers are responsible for return shipping unless the seller states otherwise.\n\n"
            "How to request a refund\n"
            "- Go to My Orders and submit a refund request with details.\n"
            "- Our team will review and coordinate with the seller.\n\n"
            "Contact: homecraft3dstore@gmail.com"
        ),
        LegalDocument.DocType.CONTENT: (
            "We require all listings and user content to be safe, lawful, and respectful.\n\n"
            "Prohibited content includes:\n"
            "- Illegal items or instructions\n"
            "- Intellectual property infringement\n"
            "- Weapons intended for harm\n"
            "- Hate, harassment, or abusive content\n"
            "- Explicit adult content\n"
            "- Malware or harmful files\n\n"
            "Seller responsibilities\n"
            "- Ensure you have rights to sell your designs.\n"
            "- Provide accurate, clear listings.\n"
            "- Respond to customer issues in a timely manner.\n\n"
            "Enforcement\n"
            "We may remove listings or suspend accounts that violate this policy.\n\n"
            "Contact: homecraft3dstore@gmail.com"
        ),
    }
    title = title_map.get(doc_type, "Legal Policy")
    return LegalDocFallback(
        title=title,
        summary="Legal policy summary",
        body=body_map.get(doc_type, "This policy is being prepared."),
        version=0,
    )


def _ctx_for(doc: LegalDocument) -> dict:
    # Provide navigation to the other latest published docs.
    docs = get_latest_published_docs()
    return {
        "doc": doc,
        "docs": docs,
    }


def terms(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.TERMS)
    return render(request, "legal/terms.html", _ctx_for(doc))


def privacy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.PRIVACY)
    return render(request, "legal/privacy.html", _ctx_for(doc))


def refund(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.REFUND)
    return render(request, "legal/refund.html", _ctx_for(doc))


def content(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_fallback(LegalDocument.DocType.CONTENT)
    return render(request, "legal/content.html", _ctx_for(doc))


@require_POST
def accept(request: HttpRequest) -> HttpResponse:
    """
    Records acceptance of all REQUIRED_DOC_TYPES in one action,
    for either logged-in user or guest_email (if provided).
    """
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not next_url:
        next_url = "/"

    guest_email = (request.POST.get("guest_email") or "").strip().lower()

    try:
        record_acceptance(request=request, user=request.user, guest_email=guest_email)
        messages.success(request, "Thanks — your acceptance has been recorded.")
    except Exception as e:
        # Keep it user-friendly.
        messages.error(request, str(e) or "Unable to record acceptance. Please try again.")
        return redirect(reverse("legal:terms") + f"?next={next_url}")

    return redirect(next_url)
