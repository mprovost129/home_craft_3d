from django.urls import path
from . import views_seller

urlpatterns = [
    path("", views_seller.seller_product_list, name="seller_list"),
    path("new/", views_seller.seller_product_create, name="seller_create"),
    path("<int:pk>/edit/", views_seller.seller_product_edit, name="seller_edit"),
    path("<int:pk>/images/", views_seller.seller_product_images, name="seller_images"),
    path("<int:pk>/images/<int:image_id>/delete/", views_seller.seller_product_image_delete, name="seller_image_delete"),
    path("<int:pk>/assets/", views_seller.seller_product_assets, name="seller_assets"),
    path("<int:pk>/assets/<int:asset_id>/delete/", views_seller.seller_product_asset_delete, name="seller_asset_delete"),
    path("<int:pk>/toggle-active/", views_seller.seller_product_toggle_active, name="seller_toggle_active"),
]
