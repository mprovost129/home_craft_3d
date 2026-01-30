from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.category_list, name="category_list"),
    path("<int:pk>/", views.category_detail, name="category_detail"),
]
