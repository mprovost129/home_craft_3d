# core/urls.py

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("coming-soon/", views.coming_soon, name="coming_soon"),
    # References (static pages now; blog/community later)
    path("references/about/", views.about_page, name="about"),
    path("references/help/", views.help_page, name="help"),
    path("references/faqs/", views.faqs_page, name="faqs"),
    path("references/tips/", views.tips_page, name="tips"),
]
