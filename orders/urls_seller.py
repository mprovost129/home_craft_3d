from django.urls import path
from . import views_seller

urlpatterns = [
    path("", views_seller.seller_orders_list, name="seller_orders_list"),
    path("<int:order_id>/", views_seller.seller_order_detail, name="seller_order_detail"),
    path("item/<int:item_id>/mark-shipped/", views_seller.seller_mark_item_shipped, name="seller_item_mark_shipped"),
]
