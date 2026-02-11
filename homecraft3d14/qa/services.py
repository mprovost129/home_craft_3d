# qa/services.py
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from products.models import Product

from .models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread

User = get_user_model()


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _thread_participants(thread: ProductQuestionThread) -> tuple[int, int]:
    buyer_id = int(thread.buyer_id)
    seller_id = int(thread.product.seller_id)
    return buyer_id, seller_id


def can_post_in_thread(*, user, thread: ProductQuestionThread) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _is_staff(user):
        return True
    buyer_id, seller_id = _thread_participants(thread)
    return int(user.id) in {buyer_id, seller_id}


def can_create_thread(*, user, product: Product) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and product and product.is_active)


@dataclass(frozen=True)
class ThreadCreateResult:
    thread: ProductQuestionThread
    first_message: ProductQuestionMessage


@transaction.atomic
def create_thread(*, product: Product, buyer, subject: str, body: str) -> ThreadCreateResult:
    """
    Create (or re-use) a thread for (product, buyer) and create the first message.
    """
    if not can_create_thread(user=buyer, product=product):
        raise PermissionDenied("You must be logged in to ask a question.")

    subject = (subject or "").strip()[:180]
    body = (body or "").strip()
    if not body:
        raise ValidationError("Message body is required.")

    # One thread per (product, buyer) (keeps things tidy on product page)
    thread, created = ProductQuestionThread.objects.get_or_create(
        product=product,
        buyer=buyer,
        defaults={"subject": subject},
    )
    if not created and subject and not thread.subject:
        thread.subject = subject
        thread.save(update_fields=["subject", "updated_at"])

    msg = ProductQuestionMessage.objects.create(
        thread=thread,
        author=buyer,
        body=body,
    )
    return ThreadCreateResult(thread=thread, first_message=msg)


@transaction.atomic
def add_reply(*, thread: ProductQuestionThread, author, body: str) -> ProductQuestionMessage:
    if thread.is_deleted:
        raise ValidationError("This Q&A thread is no longer available.")

    if not can_post_in_thread(user=author, thread=thread):
        raise PermissionDenied("You do not have permission to reply in this thread.")

    body = (body or "").strip()
    if not body:
        raise ValidationError("Reply body is required.")

    msg = ProductQuestionMessage.objects.create(thread=thread, author=author, body=body)
    # bump thread updated_at
    ProductQuestionThread.objects.filter(pk=thread.pk).update(updated_at=timezone.now())
    return msg


@transaction.atomic
def soft_delete_message(*, msg: ProductQuestionMessage, actor) -> None:
    """
    Locked spec:
    - author can delete within 30 minutes
    - after 30 minutes: staff only (upon request)
    """
    if msg.is_deleted:
        return

    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Not allowed.")

    if _is_staff(actor):
        msg.deleted_at = timezone.now()
        msg.deleted_by = actor
        msg.save(update_fields=["deleted_at", "deleted_by"])
        return

    # author-only within window
    if actor.id != msg.author_id:
        raise PermissionDenied("Not allowed.")

    if not msg.can_author_delete_now:
        raise PermissionDenied("Delete window has passed.")

    msg.deleted_at = timezone.now()
    msg.deleted_by = actor
    msg.save(update_fields=["deleted_at", "deleted_by"])


@transaction.atomic
def create_report(*, message: ProductQuestionMessage, reporter, reason: str, details: str = "") -> ProductQuestionReport:
    if not reporter or not getattr(reporter, "is_authenticated", False):
        raise PermissionDenied("You must be logged in to report content.")

    if message.is_deleted:
        raise ValidationError("Cannot report a deleted message.")

    reason = (reason or "").strip()
    details = (details or "").strip()

    if reason not in dict(ProductQuestionReport.Reason.choices):
        raise ValidationError("Invalid report reason.")

    report = ProductQuestionReport.objects.create(
        message=message,
        reporter=reporter,
        reason=reason,
        details=details,
    )
    return report


@transaction.atomic
def resolve_report(*, report: ProductQuestionReport, resolver) -> None:
    if not resolver or not getattr(resolver, "is_authenticated", False):
        raise PermissionDenied("Not allowed.")
    if not _is_staff(resolver):
        raise PermissionDenied("Staff only.")

    if report.status == ProductQuestionReport.Status.RESOLVED:
        return

    report.status = ProductQuestionReport.Status.RESOLVED
    report.resolved_at = timezone.now()
    report.resolved_by = resolver
    report.save(update_fields=["status", "resolved_at", "resolved_by"])
