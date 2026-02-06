# core/urls.py

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("coming-soon/", views.coming_soon, name="coming_soon"),
]
