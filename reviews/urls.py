from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("product/<int:product_id>/", views.product_reviews, name="product_reviews"),
    path("order-item/<int:order_item_id>/new/", views.review_create_for_order_item, name="review_for_item"),

    # Purchased-only seller rating
    path("seller/<int:order_id>/<int:seller_id>/new/", views.seller_review_create, name="seller_review_new"),
]