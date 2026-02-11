# dashboards/forms.py
from __future__ import annotations

import json

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

    # Affiliate links (friendly UI)
    # Stored as JSON list in SiteConfig.affiliate_links, edited as repeated fields here.
    AFFILIATE_LINK_ROWS = 10

    def _add_affiliate_link_fields(self) -> None:
        for i in range(1, self.AFFILIATE_LINK_ROWS + 1):
            self.fields[f"affiliate_link_{i}_label"] = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "Title"}),
            )
            self.fields[f"affiliate_link_{i}_url"] = forms.URLField(
                required=False,
                widget=forms.URLInput(attrs={"class": "form-control bg-white", "placeholder": "https://…"}),
            )
            self.fields[f"affiliate_link_{i}_note"] = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "Optional details"}),
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

    # Keep affiliate links editable outside Django admin.
    # Stored as JSON list of objects in SiteConfig.affiliate_links.

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

            # Affiliate / Amazon Associates
            "affiliate_links_enabled",
            "affiliate_links_title",
            "affiliate_disclosure_text",
            
            # Marketplace
            "marketplace_sales_percent",
            "platform_fee_cents",

            # LOCKED: free digital giveaways cap
            "free_digital_listing_cap",

            "default_currency",
            "allowed_shipping_countries_csv",
            "google_analytics_dashboard_url",
            "analytics_enabled",
            "analytics_retention_days",
            "analytics_exclude_staff",
            "analytics_exclude_admin_paths",
            "analytics_primary_host",
            "analytics_primary_environment",
            "plausible_shared_url",  # deprecated


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

            # Affiliate
            "affiliate_links_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "affiliate_links_title": forms.TextInput(attrs={"class": "form-control"}),
            "affiliate_disclosure_text": forms.TextInput(attrs={"class": "form-control"}),

            # Marketplace
            "marketplace_sales_percent": forms.NumberInput(attrs={"class": "form-control"}),
            "platform_fee_cents": forms.NumberInput(attrs={"class": "form-control"}),

            # LOCKED cap
            "free_digital_listing_cap": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 1000}
            ),

            "default_currency": forms.TextInput(attrs={"class": "form-control"}),

            # Analytics
            "google_analytics_dashboard_url": forms.URLInput(attrs={"class": "form-control"}),
            "analytics_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "analytics_primary_host": forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "homecraft3d.com"}),
            "analytics_primary_environment": forms.TextInput(attrs={"class": "form-control bg-white", "placeholder": "production"}),
            "analytics_retention_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 3650}),

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

        # Dynamic affiliate link input rows
        self._add_affiliate_link_fields()

        inst: SiteConfig | None = getattr(self, "instance", None)
        if inst and inst.pk:
            countries = getattr(inst, "allowed_shipping_countries", None) or ["US"]
            self.fields["allowed_shipping_countries_csv"].initial = ",".join(countries)

            self.fields["home_hero_title"].initial = getattr(inst, "home_hero_title", "") or ""
            self.fields["home_hero_subtitle"].initial = getattr(inst, "home_hero_subtitle", "") or ""
            # Populate affiliate link rows
            links = list(getattr(inst, "affiliate_links", None) or [])
            for idx, item in enumerate(links[: self.AFFILIATE_LINK_ROWS], start=1):
                if not isinstance(item, dict):
                    continue
                self.fields[f"affiliate_link_{idx}_label"].initial = str(item.get("label", "") or "")
                self.fields[f"affiliate_link_{idx}_url"].initial = str(item.get("url", "") or "")
                self.fields[f"affiliate_link_{idx}_note"].initial = str(item.get("note", "") or "")

    def clean_allowed_shipping_countries_csv(self) -> list[str]:
        raw = (self.cleaned_data.get("allowed_shipping_countries_csv") or "").strip()
        if not raw:
            return ["US"]
        parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
        return parts or ["US"]

    def _build_affiliate_links(self) -> list[dict]:
        links: list[dict] = []
        for i in range(1, self.AFFILIATE_LINK_ROWS + 1):
            label = (self.cleaned_data.get(f"affiliate_link_{i}_label") or "").strip()
            url = (self.cleaned_data.get(f"affiliate_link_{i}_url") or "").strip()
            note = (self.cleaned_data.get(f"affiliate_link_{i}_note") or "").strip()
            if not label and not url and not note:
                continue
            if not label or not url:
                raise forms.ValidationError("Each affiliate link row must include both a title and a URL.")
            item = {"label": label, "url": url}
            if note:
                item["note"] = note
            links.append(item)
        return links

    def save(self, commit: bool = True) -> SiteConfig:
        obj: SiteConfig = super().save(commit=False)

        # Countries
        obj.allowed_shipping_countries = self.cleaned_data.get("allowed_shipping_countries_csv") or ["US"]

        # Home hero fields (non-model fields)
        obj.home_hero_title = (self.cleaned_data.get("home_hero_title") or "").strip()
        obj.home_hero_subtitle = (self.cleaned_data.get("home_hero_subtitle") or "").strip()

        # Affiliate links (JSON)
        obj.affiliate_links = self._build_affiliate_links()

        # Affiliate links (JSON)
        obj.affiliate_links = self._build_affiliate_links()

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
