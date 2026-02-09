# orders/urls_buyer.py
from django.urls import path
from . import views_buyer

urlpatterns = [
    path("my/", views_buyer.my_orders_list, name="my_orders"),
]
