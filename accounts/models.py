from __future__ import annotations

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Profile(models.Model):
    # Public profile fields
    bio = models.TextField(blank=True, help_text="Short public bio/about for your shop.")
    website = models.URLField(blank=True, help_text="Personal or shop website.")
    social_instagram = models.URLField(blank=True, help_text="Instagram profile URL.")
    social_twitter = models.URLField(blank=True, help_text="Twitter/X profile URL.")
    social_facebook = models.URLField(blank=True, help_text="Facebook profile URL.")
    social_youtube = models.URLField(blank=True, help_text="YouTube channel URL.")
    """Marketplace Profile.

    Extends the configured AUTH_USER_MODEL with marketplace-specific profile data and role flags.

    Roles:
      - Consumer: default for any registered user
      - Seller: can list products (requires Stripe onboarding later)
      - Owner/Admin: full permissions; should be your account (can be enforced via superuser/staff too)

    Notes:
      - Public identity is username.
      - Profile is created automatically via signal (Option A).

    Seller identity:
      - Some sellers are individuals; others are a "shop".
      - `shop_name` is an optional *public* label used across the marketplace.
        If blank, we fall back to username.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    # Contact / identity
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    # Seller-facing identity (public)
    shop_name = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional public shop name. If blank, your username is shown.",
    )

    # Used for correspondence; username is public
    email = models.EmailField(blank=True)

    phone_regex = RegexValidator(
        regex=r"^[0-9\-\+\(\) ]{7,20}$",
        message="Enter a valid phone number (digits and - + ( ) allowed).",
    )
    phone_1 = models.CharField(max_length=20, blank=True, validators=[phone_regex])
    phone_2 = models.CharField(max_length=20, blank=True, validators=[phone_regex])

    address_1 = models.CharField(max_length=255, blank=True)
    address_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)

    US_STATES = [
        ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
        ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
        ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
        ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
        ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
        ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
        ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
        ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
        ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
        ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
        ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
        ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
        ("WI", "Wisconsin"), ("WY", "Wyoming"),
        ("DC", "District of Columbia"),
    ]
    state = models.CharField(max_length=2, blank=True, choices=US_STATES)
    zip_code = models.CharField(max_length=10, blank=True)

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    # Role flags
    is_seller = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)  # Owner/admin override in UI

    # Stripe (legacy placeholders; primary source of truth is payments.SellerStripeAccount)
    stripe_account_id = models.CharField(max_length=255, blank=True)
    stripe_onboarding_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_seller"]),
            models.Index(fields=["is_owner"]),
            models.Index(fields=["shop_name"]),
        ]

    def __str__(self) -> str:
        return f"Profile<{self.user.username}>"

    @property
    def display_name(self) -> str:
        # Public identity is username; name is optional
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.user.username

    @property
    def public_seller_name(self) -> str:
        """Public seller label used across the marketplace."""
        return (self.shop_name or "").strip() or self.user.username

    @property
    def can_access_seller_dashboard(self) -> bool:
        return self.is_owner or self.user.is_superuser or self.user.is_staff or self.is_seller

    @property
    def can_access_consumer_dashboard(self) -> bool:
        return self.user.is_authenticated

    @property
    def can_access_admin_dashboard(self) -> bool:
        return self.is_owner or self.user.is_superuser or self.user.is_staff