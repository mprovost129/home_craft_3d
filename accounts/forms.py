from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile


User = get_user_model()


class UsernameAuthenticationForm(AuthenticationForm):
    """Standard username/password login form (Django default)."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Username"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Password"}),
    )


class RegisterForm(UserCreationForm):
    """
    Registration form.

    - username is required (public identity)
    - optional first/last/email
    - user chooses consumer or seller
    - profile stores email + role flags (seeded at registration; rest optional)
    """

    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "First name"}),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Last name"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "Email"}),
    )

    register_as_seller = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Check this if you want to register as a seller (Stripe onboarding required later).",
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def save(self, commit: bool = True):
        user = super().save(commit=False)

        # Optional identity fields
        user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        user.last_name = (self.cleaned_data.get("last_name") or "").strip()

        email = (self.cleaned_data.get("email") or "").strip()
        if hasattr(user, "email"):
            user.email = email

        if commit:
            user.save()

        # Profile is created via signal; seed it with registration details.
        profile = getattr(user, "profile", None)
        if profile is not None:
            profile.email = email
            profile.is_seller = bool(self.cleaned_data.get("register_as_seller", False))
            profile.save(update_fields=["email", "is_seller", "updated_at"])

        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_1",
            "phone_2",
            "address_1",
            "address_2",
            "city",
            "state",
            "zip_code",
            "avatar",
            "is_seller",  # allow opt-in; Stripe gating happens elsewhere
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email"}),
            "phone_1": forms.TextInput(attrs={"placeholder": "Phone 1"}),
            "phone_2": forms.TextInput(attrs={"placeholder": "Phone 2"}),
            "address_1": forms.TextInput(attrs={"placeholder": "Address 1"}),
            "address_2": forms.TextInput(attrs={"placeholder": "Address 2"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "zip_code": forms.TextInput(attrs={"placeholder": "ZIP"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Owner/admin flags should not be editable here
        if "is_owner" in self.fields:
            self.fields.pop("is_owner")