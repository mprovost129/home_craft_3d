# qa/views.py
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import email_verified_required

from core.throttle import throttle
from core.throttle_rules import QA_THREAD_CREATE, QA_MESSAGE_REPLY, QA_REPORT, QA_DELETE
from core.models import StaffActionLog
from products.models import Product

from .forms import ReplyForm, ReportForm, ThreadCreateForm
from .models import ProductQuestionMessage, ProductQuestionReport, ProductQuestionThread
logger = logging.getLogger(__name__)

from .services import add_reply, create_report, create_thread, resolve_report, soft_delete_message


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


# ----------------------------
# Throttle rules (tune anytime)
# ----------------------------
QA_THREAD_CREATE_RULE = QA_THREAD_CREATE
QA_REPLY_RULE = QA_MESSAGE_REPLY
QA_REPORT_RULE = QA_REPORT
QA_DELETE_RULE = QA_DELETE


@require_POST
@login_required
@email_verified_required
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
@email_verified_required
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
@email_verified_required
@throttle(QA_DELETE_RULE)
def message_delete(request, message_id: int):
    msg = get_object_or_404(
        ProductQuestionMessage.objects.select_related("thread", "thread__product"),
        pk=message_id,
    )

    try:
        soft_delete_message(msg=msg, actor=request.user)
        messages.success(request, "Message deleted.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to delete message.")

    return redirect(msg.thread.product.get_absolute_url() + "#qa")


@require_POST
@login_required
@email_verified_required
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
    status = (request.GET.get("status") or "open").strip().lower()

    qs = ProductQuestionReport.objects.select_related(
        "message",
        "message__thread",
        "message__thread__product",
        "reporter",
    ).order_by("-created_at")

    if status == "resolved":
        qs = qs.filter(status=ProductQuestionReport.Status.RESOLVED)
    elif status == "all":
        qs = qs
    else:
        status = "open"
        qs = qs.filter(status=ProductQuestionReport.Status.OPEN)

    counts = {
        "open": ProductQuestionReport.objects.filter(status=ProductQuestionReport.Status.OPEN).count(),
        "resolved": ProductQuestionReport.objects.filter(status=ProductQuestionReport.Status.RESOLVED).count(),
    }

    return render(
        request,
        "qa/staff_reports_queue.html",
        {
            "reports": qs,
            "status": status,
            "counts": counts,
        },
    )


@user_passes_test(_is_staff)
@require_POST
def staff_resolve_report(request, report_id: int):
    logger.info("qa report resolved report=%s", report_id)
    report = get_object_or_404(ProductQuestionReport.objects.select_related("message"), pk=report_id)
    try:
        resolve_report(report=report, resolver=request.user)
        StaffActionLog.objects.create(
            actor=request.user,
            action=StaffActionLog.Action.QA_REPORT_RESOLVED,
            target_user=getattr(report, "reporter", None),
            qa_report=report,
            notes="Report resolved via moderation queue.",
        )
        messages.success(request, "Report resolved.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to resolve report.")

    return redirect("qa:staff_reports_queue")



@user_passes_test(_is_staff)
def staff_suspensions_list(request):
    User = get_user_model()

    suspended_users = (
        User.objects.filter(is_active=False)
        .exclude(is_staff=True)
        .exclude(is_superuser=True)
        .order_by("username")
    )

    # Fetch last suspension log per user (best-effort, lightweight)
    logs = (
        StaffActionLog.objects.filter(action=StaffActionLog.Action.USER_SUSPENDED, target_user__isnull=False)
        .select_related("actor", "target_user")
        .order_by("-created_at")
    )

    last_by_user = {}
    for log in logs:
        uid = getattr(log.target_user, "id", None)
        if uid and uid not in last_by_user:
            last_by_user[uid] = log

    rows = []
    for u in suspended_users:
        log = last_by_user.get(u.id)
        rows.append(
            {
                "user": u,
                "suspended_at": getattr(log, "created_at", None),
                "suspended_by": getattr(log, "actor", None),
                "notes": getattr(log, "notes", "") if log else "",
            }
        )

    return render(
        request,
        "qa/staff_suspensions_list.html",
        {
            "rows": rows,
        },
    )

@user_passes_test(_is_staff)
@require_POST
def staff_remove_message(request, message_id: int):
    logger.info("qa message removed message=%s", message_id)
    msg = get_object_or_404(
        ProductQuestionMessage.objects.select_related("thread", "thread__product", "author"),
        pk=message_id,
    )

    try:
        soft_delete_message(msg=msg, actor=request.user)

        # Resolve all open reports for this message (removal is a resolution).
        open_reports = ProductQuestionReport.objects.filter(message=msg, status=ProductQuestionReport.Status.OPEN)
        for r in open_reports:
            resolve_report(report=r, resolver=request.user)

        StaffActionLog.objects.create(
            actor=request.user,
            action=StaffActionLog.Action.QA_MESSAGE_REMOVED,
            target_user=msg.author,
            qa_message=msg,
            notes=f"Message removed via moderation queue. Resolved {open_reports.count()} report(s).",
        )
        messages.success(request, "Message removed and related reports resolved.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to remove message.")

    # return to queue
    return redirect("qa:staff_reports_queue")


@user_passes_test(_is_staff)
@require_POST
def staff_suspend_user(request, user_id: int):
    logger.info("qa user suspended user=%s", user_id)
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)

    try:
        if getattr(target, "is_superuser", False) or getattr(target, "is_staff", False):
            raise ValueError("You cannot suspend a staff/admin account.")

        target.is_active = False
        target.save(update_fields=["is_active"])

        # If a report_id was provided from the queue row, resolve it.
        report_id = request.POST.get("report_id")
        if report_id:
            try:
                report = ProductQuestionReport.objects.get(pk=int(report_id))
                resolve_report(report=report, resolver=request.user)
            except Exception:
                pass

        StaffActionLog.objects.create(
            actor=request.user,
            action=StaffActionLog.Action.USER_SUSPENDED,
            target_user=target,
            notes="User suspended via Q&A moderation queue.",
        )
        messages.success(request, f"User '{getattr(target, 'username', target.pk)}' suspended.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to suspend user.")

    return redirect("qa:staff_reports_queue")

@user_passes_test(_is_staff)
@require_POST
def staff_unsuspend_user(request, user_id: int):
    logger.info("qa user unsuspended user=%s", user_id)
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)

    try:
        if getattr(target, "is_superuser", False) or getattr(target, "is_staff", False):
            raise ValueError("You cannot unsuspend a staff/admin account.")

        target.is_active = True
        target.save(update_fields=["is_active"])

        StaffActionLog.objects.create(
            actor=request.user,
            action=StaffActionLog.Action.USER_UNSUSPENDED,
            target_user=target,
            notes="User unsuspended via suspensions review.",
        )
        messages.success(request, f"User '{getattr(target, 'username', target.pk)}' unsuspended.")
    except Exception as e:
        messages.error(request, str(e) or "Unable to unsuspend user.")

    return redirect("qa:staff_suspensions_list")

