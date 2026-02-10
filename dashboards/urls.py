# dashboards/urls.py
from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("consumer/", views.consumer_dashboard, name="consumer"),
    path("seller/", views.seller_dashboard, name="seller"),
    path("seller/analytics/", views.seller_analytics, name="seller_analytics"),
    path("admin/", views.admin_dashboard, name="admin"),
    path("admin/settings/", views.admin_settings, name="admin_settings"),
    path("admin/ops/", views.admin_ops, name="admin_ops"),
    path("ajax/verify-username/", views.ajax_verify_username, name="ajax_verify_username"),
]
