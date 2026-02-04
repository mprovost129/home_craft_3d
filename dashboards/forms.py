from __future__ import annotations

from django import forms

from core.models import SiteConfig


class SiteConfigForm(forms.ModelForm):
    allowed_shipping_countries_csv = forms.CharField(
        required=False,
        help_text="Comma-separated country codes (e.g. US,CA). Leave blank to default to US.",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "US"}),
    )

    class Meta:
        model = SiteConfig
        fields = [
            "marketplace_sales_percent",
            "platform_fee_cents",
            "default_currency",
            "allowed_shipping_countries_csv",
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

            # Color inputs (use <input type="color"> plus text fallback)
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

        # Initialize CSV field from JSON
        inst = getattr(self, "instance", None)
        if inst and inst.pk:
            self.fields["allowed_shipping_countries_csv"].initial = inst.allowed_shipping_countries_csv

    def clean_allowed_shipping_countries_csv(self) -> list[str]:
        raw = (self.cleaned_data.get("allowed_shipping_countries_csv") or "").strip()
        if not raw:
            return ["US"]
        parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
        return parts or ["US"]

    def save(self, commit=True):
        obj: SiteConfig = super().save(commit=False)
        obj.allowed_shipping_countries = self.cleaned_data.get("allowed_shipping_countries_csv") or ["US"]
        if commit:
            obj.save()
        return obj
