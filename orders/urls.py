# orders/urls.py

from __future__ import annotations

from django.urls import include, path

from . import views
from . import webhooks

app_name = "orders"

urlpatterns = [
    # Buyer checkout flow
    path("place/", views.place_order, name="place"),
    path("<uuid:order_id>/", views.order_detail, name="detail"),
    path("<uuid:order_id>/checkout/start/", views.checkout_start, name="checkout_start"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("<uuid:order_id>/checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    path("<uuid:order_id>/download/<uuid:asset_id>/", views.download_asset, name="download_asset"),

    # Buyer: Purchases (paid-only downloads live here)
    path("purchases/", views.purchases, name="purchases"),

    # Buyer order history (legacy/all)
    path("mine/", views.my_orders, name="my_orders"),

    # Seller fulfillment
    path("seller/orders/", views.seller_orders_list, name="seller_orders_list"),
    path("seller/orders/<uuid:order_id>/", views.seller_order_detail, name="seller_order_detail"),

    # Refunds (mounted under Orders)
    path("refunds/", include(("refunds.urls", "refunds"), namespace="refunds")),

    # Stripe webhook endpoint
    path("webhooks/stripe/", webhooks.stripe_webhook, name="stripe_webhook"),
]
