from django.urls import path

from . import views
from . import views_seller

app_name = "products"

urlpatterns = [
    # Public browsing
    path("", views.product_list, name="list"),
    path("models/", views.models_list, name="models"),
    path("files/", views.files_list, name="files"),

    # Engagement redirect endpoint (cards)
    path("go/<int:pk>/<slug:slug>/", views.product_go, name="go"),

    # Product detail (canonical)
    path("<int:pk>/<slug:slug>/", views.product_detail, name="detail"),

    # Seller area (names kept stable for templates)
    path("seller/", views_seller.seller_product_list, name="seller_list"),
    path("seller/new/", views_seller.seller_product_create, name="seller_create"),
    path("seller/<int:pk>/edit/", views_seller.seller_product_edit, name="seller_edit"),

    path("seller/<int:pk>/images/", views_seller.seller_product_images, name="seller_images"),
    path("seller/<int:pk>/images/<int:image_id>/delete/", views_seller.seller_product_image_delete, name="seller_image_delete"),

    path("seller/<int:pk>/assets/", views_seller.seller_product_assets, name="seller_assets"),
    path("seller/<int:pk>/assets/<int:asset_id>/delete/", views_seller.seller_product_asset_delete, name="seller_asset_delete"),

    path("seller/<int:pk>/toggle-active/", views_seller.seller_product_toggle_active, name="seller_toggle_active"),
]
