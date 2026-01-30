from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("product/<int:product_id>/", views.product_reviews, name="product_reviews"),
    path("create/<int:order_item_id>/", views.review_create_for_order_item, name="create_for_item"),
]
