from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class UsernameAuthenticationForm(AuthenticationForm):
    """
    Standard username/password login form (Django default).
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Username"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Password"}),
    )


class RegisterForm(UserCreationForm):
    """
    Registration form:
      - username is required (public identity)
      - user chooses consumer or seller
      - profile stores email + contact info (optional at registration)
    """

    email = forms.EmailField(required=False)
    register_as_seller = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Check this if you want to register as a seller (Stripe onboarding required later).",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def save(self, commit: bool = True):
        user = super().save(commit=commit)
        # Profile is created via signal; update it with registration details.
        profile = getattr(user, "profile", None)
        if profile:
            profile.email = self.cleaned_data.get("email", "") or ""
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
            "is_seller",  # allow user to opt-in; later we gate with Stripe onboarding
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
