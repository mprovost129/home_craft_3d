# legal/views.py
from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import LegalDocument
from .services import get_latest_published_docs, record_acceptance


def _get_latest_or_404(doc_type: str) -> LegalDocument:
    doc = (
        LegalDocument.objects.filter(doc_type=doc_type, is_published=True)
        .order_by("-version")
        .first()
    )
    if not doc:
        raise Http404("Legal document not published yet.")
    return doc


def _ctx_for(doc: LegalDocument) -> dict:
    # Provide navigation to the other latest published docs.
    docs = get_latest_published_docs()
    return {
        "doc": doc,
        "docs": docs,
    }


def terms(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_404(LegalDocument.DocType.TERMS)
    return render(request, "legal/terms.html", _ctx_for(doc))


def privacy(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_404(LegalDocument.DocType.PRIVACY)
    return render(request, "legal/privacy.html", _ctx_for(doc))


def refund(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_404(LegalDocument.DocType.REFUND)
    return render(request, "legal/refund.html", _ctx_for(doc))


def content(request: HttpRequest) -> HttpResponse:
    doc = _get_latest_or_404(LegalDocument.DocType.CONTENT)
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
