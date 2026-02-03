# qa/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "qa"

urlpatterns = [
    # Create thread + post initial question
    path("product/<uuid:product_id>/new/", views.thread_create, name="thread_create"),
    # Reply
    path("thread/<uuid:thread_id>/reply/", views.reply_create, name="reply_create"),
    # Delete a message (author window or staff)
    path("message/<uuid:message_id>/delete/", views.message_delete, name="message_delete"),
    # Report
    path("message/<uuid:message_id>/report/", views.message_report, name="message_report"),

    # Staff moderation queue/actions
    path("staff/reports/", views.staff_reports_queue, name="staff_reports_queue"),
    path("staff/reports/<uuid:report_id>/resolve/", views.staff_resolve_report, name="staff_resolve_report"),
]
