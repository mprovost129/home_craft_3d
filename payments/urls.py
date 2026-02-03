from __future__ import annotations

from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("connect/", views.connect_status, name="connect_status"),
    path("connect/start/", views.connect_start, name="connect_start"),
    path("connect/sync/", views.connect_sync, name="connect_sync"),
    path("connect/refresh/", views.connect_refresh, name="connect_refresh"),
    path("connect/return/", views.connect_return, name="connect_return"),
    # Webhook (Connect)
    path(
        "stripe/connect/webhook/",
        views.stripe_connect_webhook,
        name="stripe_connect_webhook",
    ),
    # Seller payouts / ledger
    path("payouts/", views.payouts_dashboard, name="payouts_dashboard"),
]
