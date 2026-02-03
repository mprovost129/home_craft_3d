from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("consumer/", views.consumer_dashboard, name="consumer"),
    path("seller/", views.seller_dashboard, name="seller"),
    path("admin/", views.admin_dashboard, name="admin"),
]