from __future__ import annotations

from django.urls import path

from . import views

app_name = "favorites"

urlpatterns = [
    path("", views.library, name="library"),
    path("favorite/add/<int:product_id>/", views.favorite_add, name="favorite_add"),
    path("favorite/remove/<int:product_id>/", views.favorite_remove, name="favorite_remove"),
    path("wishlist/add/<int:product_id>/", views.wishlist_add, name="wishlist_add"),
    path("wishlist/remove/<int:product_id>/", views.wishlist_remove, name="wishlist_remove"),
]
