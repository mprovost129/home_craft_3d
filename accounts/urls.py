# accounts/urls.py
from django.urls import path

from . import views
from . import views_2fa

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("profile/", views.profile_view, name="profile"),
    # 2FA URLs
    path("2fa/setup/", views_2fa.setup_2fa, name="setup_2fa"),
    path("2fa/status/", views_2fa.view_2fa_status, name="view_2fa_status"),
    path("2fa/disable/", views_2fa.disable_2fa, name="disable_2fa"),
    path("2fa/recovery-codes/", views_2fa.show_recovery_codes, name="show_recovery_codes"),
    path("2fa/regenerate-codes/", views_2fa.regenerate_recovery_codes, name="regenerate_recovery_codes"),
]
