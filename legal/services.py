# legal/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest

from .models import LegalAcceptance, LegalDocument


REQUIRED_DOC_TYPES = (
    LegalDocument.DocType.TERMS,
    LegalDocument.DocType.PRIVACY,
    LegalDocument.DocType.REFUND,
    LegalDocument.DocType.CONTENT,
)


@dataclass(frozen=True)
class LegalStatus:
    ok: bool
    missing: list[LegalDocument.DocType]
    latest_docs: dict[LegalDocument.DocType, Optional[LegalDocument]]


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _get_client_ip(request: HttpRequest) -> str | None:
    trust_proxy = bool(getattr(settings, "THROTTLE_TRUST_PROXY_HEADERS", False))
    if trust_proxy:
        xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            return xff.split(",")[0].strip() or None
    ip = (request.META.get("REMOTE_ADDR") or "").strip()
    return ip or None


def get_latest_published_docs() -> dict[LegalDocument.DocType, Optional[LegalDocument]]:
    out: dict[LegalDocument.DocType, Optional[LegalDocument]] = {}
    for dt in REQUIRED_DOC_TYPES:
        out[dt] = (
            LegalDocument.objects.filter(doc_type=dt, is_published=True)
            .order_by("-version")
            .first()
        )
    return out


def _acceptance_exists_for(*, doc: LegalDocument, user, guest_email: str) -> bool:
    qs = LegalAcceptance.objects.filter(document_id=doc.id, document_hash=doc.content_hash)
    if user and getattr(user, "is_authenticated", False):
        return qs.filter(user_id=user.id).exists()
    if guest_email:
        return qs.filter(guest_email=_norm_email(guest_email)).exists()
    return False


def check_legal_acceptance(*, request: HttpRequest, user, guest_email: str = "") -> LegalStatus:
    docs = get_latest_published_docs()
    missing: list[LegalDocument.DocType] = []
    for dt, doc in docs.items():
        if doc is None:
            missing.append(dt)
            continue
        if not _acceptance_exists_for(doc=doc, user=user, guest_email=guest_email):
            missing.append(dt)

    return LegalStatus(ok=(len(missing) == 0), missing=missing, latest_docs=docs)


@transaction.atomic
def record_acceptance(*, request: HttpRequest, user, guest_email: str = "") -> None:
    docs = get_latest_published_docs()
    if any(d is None for d in docs.values()):
        raise ValidationError("Legal documents are not published yet.")

    ip = _get_client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    guest_email_norm = _norm_email(guest_email)

    for _, doc in docs.items():
        assert doc is not None
        if _acceptance_exists_for(doc=doc, user=user, guest_email=guest_email_norm):
            continue

        LegalAcceptance.objects.create(
            document=doc,
            user=user if (user and getattr(user, "is_authenticated", False)) else None,
            guest_email=guest_email_norm,
            ip_address=ip,
            user_agent=ua,
            document_hash=doc.content_hash,
        )
