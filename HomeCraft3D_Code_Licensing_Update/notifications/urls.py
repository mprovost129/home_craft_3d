# notifications/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("<int:pk>/unread/", views.mark_unread, name="mark_unread"),
    path("clear-read/", views.clear_all_read, name="clear_all_read"),
]
