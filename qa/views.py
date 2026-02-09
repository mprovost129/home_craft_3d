# qa/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.throttle import ThrottleRule, throttle
from products.models import Product

from .forms import ReplyForm, ReportForm, ThreadCreateForm
from .models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread
from .services import add_reply, create_report, create_thread, resolve_report, soft_delete_message


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


# ----------------------------
# Throttle rules (tune anytime)
# ----------------------------
QA_THREAD_CREATE_RULE = ThrottleRule(key_prefix="qa_thread_create", limit=3, window_seconds=60)
QA_REPLY_RULE = ThrottleRule(key_prefix="qa_reply_create", limit=6, window_seconds=60)
QA_REPORT_RULE = ThrottleRule(key_prefix="qa_message_report", limit=3, window_seconds=60)
QA_DELETE_RULE = ThrottleRule(key_prefix="qa_message_delete", limit=8, window_seconds=60)


@require_POST
@login_required
@throttle(QA_THREAD_CREATE_RULE)
def thread_create(request, product_id: int):
    product = get_object_or_404(Product.objects.filter(is_active=True), pk=product_id)
    form = ThreadCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the form.")
        return redirect(product.get_absolute_url() + "#qa")

    try:
        create_thread(
            product=product,
            buyer=request.user,
            subject=form.cleaned_data.get("subject", ""),
            body=form.cleaned_data["body"],
        )
        messages.success(request, "Question posted.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to post question.")

    return redirect(product.get_absolute_url() + "#qa")


@require_POST
@login_required
@throttle(QA_REPLY_RULE)
def reply_create(request, thread_id: int):
    thread = get_object_or_404(
        ProductQuestionThread.objects.select_related("product", "product__seller", "buyer"),
        pk=thread_id,
        deleted_at__isnull=True,
    )

    form = ReplyForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the reply.")
        return redirect(thread.product.get_absolute_url() + "#qa")

    try:
        add_reply(thread=thread, author=request.user, body=form.cleaned_data["body"])
        messages.success(request, "Reply posted.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to reply.")

    return redirect(thread.product.get_absolute_url() + "#qa")


@require_POST
@login_required
@throttle(QA_DELETE_RULE)
def message_delete(request, message_id: int):
    msg = get_object_or_404(
        ProductQuestionMessage.objects.select_related("thread", "thread__product"),
        pk=message_id,
    )

    try:
        soft_delete_message(message=msg, actor=request.user)
        messages.success(request, "Message deleted.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to delete message.")

    return redirect(msg.thread.product.get_absolute_url() + "#qa")


@require_POST
@login_required
@throttle(QA_REPORT_RULE)
def message_report(request, message_id: int):
    msg = get_object_or_404(
        ProductQuestionMessage.objects.select_related("thread", "thread__product"),
        pk=message_id,
        deleted_at__isnull=True,
    )

    form = ReportForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the report.")
        return redirect(msg.thread.product.get_absolute_url() + "#qa")

    try:
        create_report(
            message=msg,
            reporter=request.user,
            reason=form.cleaned_data["reason"],
            details=form.cleaned_data.get("details", ""),
        )
        messages.success(request, "Report submitted. Staff will review it.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to submit report.")

    return redirect(msg.thread.product.get_absolute_url() + "#qa")


@user_passes_test(_is_staff)
def staff_reports_queue(request):
    qs = (
        ProductQuestionReport.objects.select_related(
            "message",
            "message__thread",
            "message__thread__product",
            "reporter",
        )
        .filter(status=ProductQuestionReport.Status.OPEN)
        .order_by("-created_at")
    )

    return render(request, "qa/staff_reports_queue.html", {"reports": qs})


@user_passes_test(_is_staff)
@require_POST
def staff_resolve_report(request, report_id: int):
    report = get_object_or_404(ProductQuestionReport.objects.select_related("message"), pk=report_id)
    try:
        resolve_report(report=report, actor=request.user)
        messages.success(request, "Report resolved.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to resolve report.")

    return redirect("qa:staff_reports_queue")
