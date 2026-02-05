# dashboards/forms.py
from __future__ import annotations

from django import forms

from core.models import SiteConfig


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
            attrs={
                "class": "form-control",
                "placeholder": "Welcome to Home Craft 3D",
            }
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
            # Marketplace
            "marketplace_sales_percent",
            "platform_fee_cents",
            "default_currency",
            "allowed_shipping_countries_csv",

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
            "marketplace_sales_percent": forms.NumberInput(attrs={"class": "form-control"}),
            "platform_fee_cents": forms.NumberInput(attrs={"class": "form-control"}),
            "default_currency": forms.TextInput(attrs={"class": "form-control"}),

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

            "facebook_url": forms.URLInput(attrs={"class": "form-control"}),
            "instagram_url": forms.URLInput(attrs={"class": "form-control"}),
            "tiktok_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_url": forms.URLInput(attrs={"class": "form-control"}),
            "x_url": forms.URLInput(attrs={"class": "form-control"}),
            "linkedin_url": forms.URLInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        inst: SiteConfig | None = getattr(self, "instance", None)
        if inst and inst.pk:
            # Render allowed_shipping_countries list as CSV
            countries = getattr(inst, "allowed_shipping_countries", None) or ["US"]
            self.fields["allowed_shipping_countries_csv"].initial = ",".join(countries)

            # Home hero fields come from DB fields on SiteConfig
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

        # Persist countries list
        obj.allowed_shipping_countries = self.cleaned_data.get("allowed_shipping_countries_csv") or ["US"]

        # Persist home hero fields onto SiteConfig
        obj.home_hero_title = (self.cleaned_data.get("home_hero_title") or "").strip()
        obj.home_hero_subtitle = (self.cleaned_data.get("home_hero_subtitle") or "").strip()

        if commit:
            obj.save()

        return obj
