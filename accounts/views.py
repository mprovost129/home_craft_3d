# accounts/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.throttle import ThrottleRule, throttle
from .forms import RegisterForm, UsernameAuthenticationForm, ProfileForm


# ----------------------------
# Throttle rules (tune anytime)
# ----------------------------
AUTH_LOGIN_RULE = ThrottleRule(key_prefix="auth_login", limit=10, window_seconds=60)
AUTH_REGISTER_RULE = ThrottleRule(key_prefix="auth_register", limit=5, window_seconds=60)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        # throttle only the POST attempt
        return _login_post(request)

    form = UsernameAuthenticationForm(request)
    return render(request, "accounts/login.html", {"form": form})


@require_POST
@throttle(AUTH_LOGIN_RULE)
def _login_post(request):
    form = UsernameAuthenticationForm(request, data=request.POST)
    if form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, "Welcome back.")
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("core:home")
        return redirect(next_url)

    # Optional: generic message to avoid hinting “user exists”
    messages.error(request, "Invalid credentials.")
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    if request.method == "POST":
        return _register_post(request)

    form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@require_POST
@throttle(AUTH_REGISTER_RULE)
def _register_post(request):
    form = RegisterForm(request.POST)
    if form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created.")
        
        # If user registered as seller, redirect to Stripe onboarding
        if form.cleaned_data.get("register_as_seller"):
            messages.info(request, "Let's set up your seller account with Stripe.")
            return redirect("payments:connect_start")
        
        return redirect("accounts:profile")

    messages.error(request, "Please correct the form.")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile_view(request):
    # Profile is created via signal; assume it exists.
    profile = request.user.profile

    if request.method == "POST":
        # Track if they're enabling seller mode for the first time
        was_seller = profile.is_seller
        
        form = ProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            
            # If they just enabled seller mode, redirect to Stripe onboarding
            is_now_seller = form.cleaned_data.get("is_seller", False)
            if is_now_seller and not was_seller:
                messages.info(request, "Let's set up your seller account with Stripe.")
                return redirect("payments:connect_start")
            
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=profile, user=request.user)

    return render(request, "accounts/profile.html", {"form": form, "profile": profile})
