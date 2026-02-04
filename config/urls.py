# config/urls.py

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
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

handler400 = "core.views.error_400"
handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
