# products/urls.py
from django.urls import path

from . import views
from . import views_seller

app_name = "products"

urlpatterns = [
    # Public browsing
    path("", views.product_list, name="list"),
    path("models/", views.models_list, name="models"),
    path("files/", views.files_list, name="files"),

    # Top sellers page
    path("top-sellers/", views.top_sellers, name="top_sellers"),

    # Seller shop page
    path("shop/<int:seller_id>/", views.seller_shop, name="seller_shop"),

    # Engagement redirect (logs CLICK then redirects to detail)
    path("go/<int:pk>/<slug:slug>/", views.product_go, name="go"),

    # Canonical detail
    path("<int:pk>/<slug:slug>/", views.product_detail, name="detail"),

    # Seller area
    path("seller/", views_seller.seller_product_list, name="seller_list"),
    path("seller/new/", views_seller.seller_product_create, name="seller_create"),
    path("seller/<int:pk>/edit/", views_seller.seller_product_edit, name="seller_edit"),
    path("seller/<int:pk>/preview/", views_seller.seller_product_preview, name="seller_preview"),
    path("seller/<int:pk>/specs/", views_seller.seller_product_specs, name="seller_specs"),
    path("seller/<int:pk>/duplicate/", views_seller.seller_product_duplicate, name="seller_duplicate"),

    path("seller/<int:pk>/images/", views_seller.seller_product_images, name="seller_images"),
    path("seller/<int:pk>/images/<int:image_id>/delete/", views_seller.seller_product_image_delete, name="seller_image_delete"),
    path("seller/<int:pk>/images/<int:image_id>/update/", views_seller.seller_product_image_update, name="seller_image_update"),

    path("seller/<int:pk>/assets/", views_seller.seller_product_assets, name="seller_assets"),
    path("seller/<int:pk>/assets/<int:asset_id>/delete/", views_seller.seller_product_asset_delete, name="seller_asset_delete"),

    path("seller/<int:pk>/toggle-active/", views_seller.seller_product_toggle_active, name="seller_toggle_active"),
    path("seller/<int:pk>/delete/", views_seller.seller_product_delete, name="seller_delete"),
    path(
        "<int:pk>/<slug:slug>/assets/<int:asset_id>/download/",
        views.product_free_asset_download,
        name="free_asset_download",
    ),

    # Dependent dropdown endpoint (Category -> Subcategory)
    path("seller/subcategories/", views_seller.seller_subcategories_for_category, name="seller_subcategories_for_category"),
]
