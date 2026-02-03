# legal/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("refund/", views.refund, name="refund"),
    path("content/", views.content, name="content"),

    # Records acceptance of all required docs, then redirects back to ?next=
    path("accept/", views.accept, name="accept"),
]
