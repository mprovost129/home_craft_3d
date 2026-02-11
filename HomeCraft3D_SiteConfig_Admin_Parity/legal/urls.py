# legal/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    path("", views.index, name="index"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("refund/", views.refund, name="refund"),
    path("content/", views.content, name="content"),
    path("digital-license/", views.digital_license, name="digital_license"),
    path("seller-agreement/", views.seller_agreement, name="seller_agreement"),
    path("physical-policy/", views.physical_policy, name="physical_policy"),

    # Records acceptance of all required docs, then redirects back to ?next=
    path("accept/", views.accept, name="accept"),
]
