# dashboards/forms.py
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from core.models import SiteConfig
from products.models import Product

from .models import ProductFreeUnlock


class SiteConfigForm(forms.ModelForm):
    """
    Admin Settings form (non-Django-admin UI) for DB-backed SiteConfig.
    """

    allowed_shipping_countries_csv = forms.CharField(
        required=False,
        help_text="Comma-separated country codes (e.g. US,CA). Leave blank to default to US.",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "US"}),
    )

    home_hero_title = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Welcome to Home Craft 3D"}
        ),
        help_text="Shown as the big headline on the home page.",
    )

    home_hero_subtitle = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describe what buyers can do on your marketplace…",
            }
        ),
        help_text="Shown under the hero title on the home page.",
    )

    class Meta:
        model = SiteConfig
        fields = [
            # Promo banner (sitewide above navbar)
            "promo_banner_enabled",
            "promo_banner_text",

            # Home page banner (home page only)
            "home_banner_enabled",
            "home_banner_text",

            # Seller waiver promo
            "seller_fee_waiver_enabled",
            "seller_fee_waiver_days",

            # Marketplace
            "marketplace_sales_percent",
            "platform_fee_cents",

            # LOCKED: free digital giveaways cap
            "free_digital_listing_cap",

            "default_currency",
            "allowed_shipping_countries_csv",
            "plausible_shared_url",

            # Home page
            "home_hero_title",
            "home_hero_subtitle",

            # Theme
            "theme_default_mode",
            "theme_primary",
            "theme_accent",
            "theme_success",
            "theme_danger",
            "theme_light_bg",
            "theme_light_surface",
            "theme_light_text",
            "theme_light_text_muted",
            "theme_light_border",
            "theme_dark_bg",
            "theme_dark_surface",
            "theme_dark_text",
            "theme_dark_text_muted",
            "theme_dark_border",

            # Social
            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "x_url",
            "linkedin_url",
        ]

        widgets = {
            # Promo banner (sitewide)
            "promo_banner_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "promo_banner_text": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Sellers pay 0% fees for 30 days!",
                }
            ),

            # Home page banner (home only)
            "home_banner_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "home_banner_text": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: First 30 days FREE!",
                }
            ),

            # Waiver
            "seller_fee_waiver_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "seller_fee_waiver_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 365}
            ),

            # Marketplace
            "marketplace_sales_percent": forms.NumberInput(attrs={"class": "form-control"}),
            "platform_fee_cents": forms.NumberInput(attrs={"class": "form-control"}),

            # LOCKED cap
            "free_digital_listing_cap": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 1000}
            ),

            "default_currency": forms.TextInput(attrs={"class": "form-control"}),

            # Theme
            "theme_default_mode": forms.Select(attrs={"class": "form-select"}),

            "theme_primary": forms.TextInput(attrs={"class": "form-control", "placeholder": "#F97316"}),
            "theme_accent": forms.TextInput(attrs={"class": "form-control", "placeholder": "#F97316"}),
            "theme_success": forms.TextInput(attrs={"class": "form-control", "placeholder": "#16A34A"}),
            "theme_danger": forms.TextInput(attrs={"class": "form-control", "placeholder": "#DC2626"}),

            "theme_light_bg": forms.TextInput(attrs={"class": "form-control"}),
            "theme_light_surface": forms.TextInput(attrs={"class": "form-control"}),
            "theme_light_text": forms.TextInput(attrs={"class": "form-control"}),
            "theme_light_text_muted": forms.TextInput(attrs={"class": "form-control"}),
            "theme_light_border": forms.TextInput(attrs={"class": "form-control"}),

            "theme_dark_bg": forms.TextInput(attrs={"class": "form-control"}),
            "theme_dark_surface": forms.TextInput(attrs={"class": "form-control"}),
            "theme_dark_text": forms.TextInput(attrs={"class": "form-control"}),
            "theme_dark_text_muted": forms.TextInput(attrs={"class": "form-control"}),
            "theme_dark_border": forms.TextInput(attrs={"class": "form-control"}),

            # Social
            "facebook_url": forms.URLInput(attrs={"class": "form-control"}),
            "instagram_url": forms.URLInput(attrs={"class": "form-control"}),
            "tiktok_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_url": forms.URLInput(attrs={"class": "form-control"}),
            "x_url": forms.URLInput(attrs={"class": "form-control"}),
            "linkedin_url": forms.URLInput(attrs={"class": "form-control"}),

            "plausible_shared_url": forms.URLInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        inst: SiteConfig | None = getattr(self, "instance", None)
        if inst and inst.pk:
            countries = getattr(inst, "allowed_shipping_countries", None) or ["US"]
            self.fields["allowed_shipping_countries_csv"].initial = ",".join(countries)

            self.fields["home_hero_title"].initial = getattr(inst, "home_hero_title", "") or ""
            self.fields["home_hero_subtitle"].initial = getattr(inst, "home_hero_subtitle", "") or ""

    def clean_allowed_shipping_countries_csv(self) -> list[str]:
        raw = (self.cleaned_data.get("allowed_shipping_countries_csv") or "").strip()
        if not raw:
            return ["US"]
        parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
        return parts or ["US"]

    def save(self, commit: bool = True) -> SiteConfig:
        obj: SiteConfig = super().save(commit=False)

        # Countries
        obj.allowed_shipping_countries = self.cleaned_data.get("allowed_shipping_countries_csv") or ["US"]

        # Home hero fields (non-model fields)
        obj.home_hero_title = (self.cleaned_data.get("home_hero_title") or "").strip()
        obj.home_hero_subtitle = (self.cleaned_data.get("home_hero_subtitle") or "").strip()

        # Banner housekeeping (both banners)
        obj.promo_banner_text = (obj.promo_banner_text or "").strip()
        if not obj.promo_banner_enabled:
            obj.promo_banner_text = ""

        obj.home_banner_text = (obj.home_banner_text or "").strip()
        if not obj.home_banner_enabled:
            obj.home_banner_text = ""

        if commit:
            obj.save()

        return obj


class ProductFreeUnlockForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label="Product",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    username = forms.CharField(
        label="Username",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    user_email = forms.EmailField(
        label="User Email",
        required=False,
        widget=forms.EmailInput(attrs={"readonly": "readonly", "class": "form-control"}),
    )
    send_email = forms.BooleanField(
        label="Send download email?",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        seller = kwargs.pop("seller", None)
        super().__init__(*args, **kwargs)
        if seller:
            self.fields["product"].queryset = Product.objects.filter(seller=seller)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        User = get_user_model()
        try:
            user = User.objects.get(username=username, is_active=True)
            cleaned_data["user"] = user
            cleaned_data["user_email"] = user.email
        except User.DoesNotExist:
            self.add_error("username", "No active user found with this username.")
        return cleaned_data

    def save(self, seller):
        product = self.cleaned_data["product"]
        user = self.cleaned_data["user"]
        unlock, created = ProductFreeUnlock.objects.get_or_create(
            product=product, user=user, defaults={"granted_by": seller}
        )
        return unlock, created
