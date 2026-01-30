from django.urls import path, include
from . import views

app_name = "orders"

urlpatterns = [
    # Buyer history
    path("", include("orders.urls_buyer")),

    # Checkout / order creation
    path("place/", views.place_order, name="place"),
    path("<int:order_id>/", views.order_detail, name="detail"),

    # Stripe checkout
    path("<int:order_id>/checkout/start/", views.checkout_start, name="checkout_start"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/cancel/<int:order_id>/", views.checkout_cancel, name="checkout_cancel"),

    # Downloads gating (digital assets)
    path("<int:order_id>/download/<int:asset_id>/", views.download_asset, name="download_asset"),

    # Seller fulfillment
    path("seller/", include("orders.urls_seller")),

    # Webhook
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
