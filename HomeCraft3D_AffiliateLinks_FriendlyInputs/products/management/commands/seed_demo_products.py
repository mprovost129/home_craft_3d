# products/management/commands/seed_demo_products.py
from __future__ import annotations

import base64
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from products.models import Product, ProductImage

# Optional models in your project
try:
    from payments.models import SellerStripeAccount
except Exception:  # pragma: no cover
    SellerStripeAccount = None  # type: ignore

try:
    from catalog.models import Category
except Exception:  # pragma: no cover
    Category = None  # type: ignore


# 1x1 PNG (transparent) to attach to ImageField so UI renders
_ONE_BY_ONE_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


class Command(BaseCommand):
    help = "Seed demo sellers + categories + products + images for local smoke testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--products",
            type=int,
            default=12,
            help="Total products to create (default 12). Will split evenly between MODEL and FILE when possible.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo users/products created by this command before reseeding.",
        )

    def handle(self, *args, **options):
        total_products: int = max(2, int(options["products"]))
        reset: bool = bool(options["reset"])

        with transaction.atomic():
            seller_ready = self._get_or_create_user(
                username="demo_seller_ready",
                email="demo_seller_ready@example.com",
                password="demo12345",
                is_staff=True,
            )
            seller_not_ready = self._get_or_create_user(
                username="demo_seller_not_ready",
                email="demo_seller_not_ready@example.com",
                password="demo12345",
                is_staff=True,
            )

            if reset:
                self._reset_demo_data({seller_ready.id, seller_not_ready.id})

            self._ensure_seller_ready_flag(seller_ready)

            model_cat = self._get_or_create_category_for_kind("MODEL", name="Demo Models")
            file_cat = self._get_or_create_category_for_kind("FILE", name="Demo Files")

            # Split products roughly evenly
            n_model = total_products // 2
            n_file = total_products - n_model

            created = 0
            created += self._seed_products_for_kind(
                seller=seller_ready,
                kind="MODEL",
                category=model_cat,
                count=max(1, n_model // 2),
                title_prefix="Ready Model",
                price_base=Decimal("24.99"),
                featured=True,
            )
            created += self._seed_products_for_kind(
                seller=seller_not_ready,
                kind="MODEL",
                category=model_cat,
                count=max(1, n_model - (n_model // 2)),
                title_prefix="NotReady Model",
                price_base=Decimal("19.99"),
                featured=False,
            )
            created += self._seed_products_for_kind(
                seller=seller_ready,
                kind="FILE",
                category=file_cat,
                count=max(1, n_file // 2),
                title_prefix="Ready File",
                price_base=Decimal("4.99"),
                featured=False,
            )
            created += self._seed_products_for_kind(
                seller=seller_not_ready,
                kind="FILE",
                category=file_cat,
                count=max(1, n_file - (n_file // 2)),
                title_prefix="NotReady File",
                price_base=Decimal("3.99"),
                featured=False,
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("Demo logins:")
        self.stdout.write("  demo_seller_ready / demo12345  (Stripe-ready where supported)")
        self.stdout.write("  demo_seller_not_ready / demo12345")
        self.stdout.write(f"Created/ensured ~{created} products + images.")

    def _get_or_create_user(self, *, username: str, email: str, password: str, is_staff: bool) -> object:
        User = get_user_model()

        # Try to find by username or email
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(email=email).first()

        if user:
            # Ensure basics
            if getattr(user, "username", None) != username:
                try:
                    user.username = username  # type: ignore[attr-defined]
                except Exception:
                    pass
            if getattr(user, "email", None) != email:
                try:
                    user.email = email
                except Exception:
                    pass
            try:
                user.is_staff = bool(is_staff)
            except Exception:
                pass
            user.save()
            return user

        # Create
        try:
            user = User.objects.create_user(username=username, email=email, password=password)
        except TypeError:
            # If custom user creation differs, fallback to minimal create + set_password
            user = User(username=username, email=email)
            user.set_password(password)
            user.save()

        try:
            user.is_staff = bool(is_staff)
            user.save()
        except Exception:
            pass

        return user

    def _reset_demo_data(self, seller_ids: set[int]) -> None:
        # Delete demo products for our demo sellers
        qs = Product.objects.filter(seller_id__in=seller_ids)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.WARNING(f"Reset: deleted {count} existing demo products."))

    def _ensure_seller_ready_flag(self, seller) -> None:
        if SellerStripeAccount is None:
            self.stdout.write(self.style.WARNING("SellerStripeAccount model not available; skipping ready flag."))
            return

        try:
            SellerStripeAccount.objects.update_or_create(
                user_id=seller.id,
                defaults={
                    "charges_enabled": True,
                    "payouts_enabled": True,
                    "details_submitted": True,
                },
            )
        except Exception:
            self.stdout.write(self.style.WARNING("Could not set Stripe readiness flags (schema mismatch)."))

    def _get_or_create_category_for_kind(self, kind: str, *, name: str):
        """
        Best-effort:
        - Prefer existing categories for the requested kind/type.
        - If none exist and Category model is compatible, create a simple root category.
        """
        if Category is None:
            self.stdout.write(self.style.WARNING("Category model not available; cannot attach categories."))
            return None

        # First: try to find anything matching kind
        # Your Category probably has CategoryType MODEL/FILE stored in field `type`.
        cat = None
        try:
            cat = Category.objects.filter(type=kind).order_by("id").first()
        except Exception:
            cat = None

        if cat:
            return cat

        # Try to create a minimal category. This depends on your schema.
        data = {}
        # Common fields
        if hasattr(Category, "name"):
            data["name"] = name
        if hasattr(Category, "slug"):
            data["slug"] = slugify(name)
        if hasattr(Category, "type"):
            data["type"] = kind
        # Tree fields (optional)
        if hasattr(Category, "parent_id"):
            data["parent_id"] = None

        try:
            return Category.objects.create(**data)
        except Exception:
            self.stdout.write(self.style.WARNING(f"Could not auto-create Category for kind={kind}; using first available."))
            try:
                return Category.objects.order_by("id").first()
            except Exception:
                return None

    def _seed_products_for_kind(
        self,
        *,
        seller,
        kind: str,
        category,
        count: int,
        title_prefix: str,
        price_base: Decimal,
        featured: bool,
    ) -> int:
        created = 0
        for i in range(1, count + 1):
            title = f"{title_prefix} #{i}"
            slug = slugify(title)[:180]

            # Ensure uniqueness per seller+slug
            existing = Product.objects.filter(seller_id=seller.id, slug=slug).first()
            if existing:
                p = existing
                p.title = title
                p.kind = kind
                if category is not None:
                    p.category = category
                p.price = price_base + Decimal(i)
                p.is_free = False
                p.is_active = True
                p.is_featured = bool(featured and i <= 2)
                p.is_trending = bool(i == 1)  # seed a couple manual trending flags
                p.short_description = "Seeded demo listing for UI testing."
                p.description = "This is demo data generated by seed_demo_products."
                p.save()
            else:
                kwargs = dict(
                    seller_id=seller.id,
                    kind=kind,
                    title=title,
                    slug=slug,
                    short_description="Seeded demo listing for UI testing.",
                    description="This is demo data generated by seed_demo_products.",
                    price=price_base + Decimal(i),
                    is_free=False,
                    is_active=True,
                    is_featured=bool(featured and i <= 2),
                    is_trending=bool(i == 1),
                )
                if category is not None:
                    kwargs["category"] = category
                p = Product.objects.create(**kwargs)

            # Ensure an image exists
            if not p.images.exists():
                img_name = f"demo_{p.kind.lower()}_{p.id}.png"
                content = ContentFile(_ONE_BY_ONE_PNG, name=img_name)
                ProductImage.objects.create(
                    product=p,
                    image=content,
                    alt_text=p.title,
                    is_primary=True,
                    sort_order=0,
                )

            created += 1

        return created
