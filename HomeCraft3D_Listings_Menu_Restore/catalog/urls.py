# catalog/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    # Public pages
    path("", views.category_list, name="category_list"),
    path("<int:pk>/", views.category_detail, name="category_detail"),

    # API for dependent dropdowns
    path("api/categories/", views.api_categories, name="api_categories"),
    path("api/subcategories/", views.api_subcategories, name="api_subcategories"),
]
