# config/urls.py

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core_views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("catalog/", include("catalog.urls")),
    path("products/", include("products.urls")),
    path("cart/", include("cart.urls")),
    path("legal/", include(("legal.urls", "legal"), namespace="legal")),

    # Orders include refunds under /orders/refunds/ via orders.urls
    path("orders/", include("orders.urls")),

    # Stripe Connect onboarding
    path("payments/", include("payments.urls")),

    path("reviews/", include("reviews.urls")),
    path("qa/", include("qa.urls")),          # ✅ IMPORTANT: add Q&A routes
    path("dashboard/", include("dashboards.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
