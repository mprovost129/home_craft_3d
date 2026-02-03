# refunds/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "refunds"

urlpatterns = [
    # Buyer/Guest: create request (physical-only)
    # IMPORTANT: keep this ABOVE the "<uuid:refund_id>/" route to avoid URL shadowing.
    path("new/<uuid:order_id>/<uuid:item_id>/", views.buyer_create, name="buyer_create"),

    # Seller: queue + detail + actions
    path("seller/", views.seller_queue, name="seller_queue"),
    path("seller/<uuid:refund_id>/", views.seller_detail, name="seller_detail"),
    path("seller/<uuid:refund_id>/approve/", views.seller_approve, name="seller_approve"),
    path("seller/<uuid:refund_id>/decline/", views.seller_decline, name="seller_decline"),
    path("seller/<uuid:refund_id>/refund/", views.seller_trigger_refund, name="seller_trigger_refund"),

    # Staff safety valve
    path("staff/", views.staff_queue, name="staff_queue"),
    path("staff/<uuid:refund_id>/refund/", views.staff_trigger_refund, name="staff_trigger_refund"),

    # Buyer: list + detail (keep detail last)
    path("", views.buyer_list, name="buyer_list"),
    path("<uuid:refund_id>/", views.buyer_detail, name="buyer_detail"),
]
