# products/views_seller.py
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional, List, Tuple

from django.contrib import messages
from django.core.files import File
from django.db import transaction
from django.db.models import Q, Sum, F, IntegerField, Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from catalog.models import Category
from core.throttle import ThrottleRule, throttle
from payments.models import SellerStripeAccount

from .forms import (
    ProductForm,
    ProductImageUploadForm,
    ProductImageBulkUploadForm,
    DigitalAssetUploadForm,
    ProductPhysicalForm,
    ProductDigitalForm,
)
from .models import Product, ProductImage, DigitalAsset, ALLOWED_ASSET_EXTS
from .permissions import seller_required, is_owner_user
from .views import _render_product_detail


SELLER_PRODUCT_MUTATE_RULE = ThrottleRule(key_prefix="seller_product_mutate", limit=20, window_seconds=60)
SELLER_UPLOAD_RULE = ThrottleRule(key_prefix="seller_upload", limit=12, window_seconds=60)
SELLER_DELETE_RULE = ThrottleRule(key_prefix="seller_delete", limit=20, window_seconds=60)
SELLER_CATEGORY_AJAX_RULE = ThrottleRule(key_prefix="seller_category_ajax", limit=60, window_seconds=60)


def _file_type_options() -> list[str]:
    preferred = ["stl", "3mf", "obj", "zip"]
    allowed = [t for t in preferred if t in ALLOWED_ASSET_EXTS] + sorted(
        t for t in ALLOWED_ASSET_EXTS if t not in preferred
    )
    return allowed


def _can_edit_product(user, product: Product) -> bool:
    if is_owner_user(user):
        return True
    return product.seller == user


def _get_owned_product_or_404(request, pk: int) -> Product:
    product = get_object_or_404(Product, pk=pk)
    if not _can_edit_product(request.user, product):
        raise Http404("Not found")
    return product


def _publish_checklist(product: Product) -> tuple[bool, list[str]]:
    """
    Return (is_publishable, missing_items).

    LOCKED RULE:
    - Drafts can be edited freely.
    - A listing cannot be made active until required setup is complete.
    """
    missing: list[str] = []

    # Required basics
    if not (product.title or "").strip():
        missing.append("Title")
    if not product.category_id:
        missing.append("Category")
    if not (product.short_description or "").strip():
        missing.append("Short description")
    if not (product.description or "").strip():
        missing.append("Description")

    # Images
    if not product.images.exists():
        missing.append("At least 1 image")
    else:
        if not product.images.filter(is_primary=True).exists():
            missing.append("Primary image")

    # Kind-specific requirements
    if product.kind == Product.Kind.MODEL:
        # Specs must exist
        try:
            _ = product.physical
        except Exception:
            missing.append("Physical specs")
    elif product.kind == Product.Kind.FILE:
        try:
            _ = product.digital
        except Exception:
            missing.append("Digital specs")
        if not product.digital_assets.exists():
            missing.append("At least 1 digital asset")

    # Price rules
    if not product.is_free:
        try:
            if product.price is None or product.price <= 0:
                missing.append("Price > 0 (or mark Free)")
        except Exception:
            missing.append("Valid price (or mark Free)")

    return (len(missing) == 0), missing


def _safe_storage_copy(*, source_field, dest_prefix: str) -> Optional[str]:
    """
    Copy a stored FileField/ImageField to a new name under dest_prefix.

    Returns the new storage name (string) or None if copy fails.
    """
    if not source_field:
        return None
    try:
        src_name = getattr(source_field, "name", "") or ""
        if not src_name:
            return None

        suffix = Path(src_name).suffix.lower()
        new_name = f"{dest_prefix}/{uuid.uuid4().hex}{suffix}"

        with source_field.open("rb") as f:
            saved_name = source_field.storage.save(new_name, File(f))
        return saved_name
    except Exception:
        return None


@seller_required
def seller_product_list(request, *args, **kwargs):
    """
    Seller dashboard: list your products.
    Owner/admin sees all products.
    """
    qs = (
        Product.objects.select_related("seller", "category", "category__parent")
        .prefetch_related("images", "digital_assets")
        .annotate(
            paid_qty=Coalesce(
                Sum(
                    "order_items__quantity",
                    filter=Q(
                        order_items__order__status="PAID",
                        order_items__order__paid_at__isnull=False,
                        order_items__is_tip=False,
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
            refunded_qty=Coalesce(
                Sum(
                    "order_items__quantity",
                    filter=Q(order_items__refund_request__status="refunded"),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
            units_sold=ExpressionWrapper(
                F("paid_qty") - F("refunded_qty"),
                output_field=IntegerField(),
            ),
        )
        .order_by("-created_at")
    )

    if not is_owner_user(request.user):
        qs = qs.filter(seller=request.user)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )

    file_type = (request.GET.get("file_type") or "").strip().lower().lstrip(".")
    if file_type:
        qs = qs.filter(
            Q(digital_assets__file_type=file_type) | Q(digital_assets__file__iendswith=f".{file_type}")
        ).distinct()

    stripe_account = None
    stripe_ready = True
    if not is_owner_user(request.user):
        stripe_account = SellerStripeAccount.objects.filter(user=request.user).first()
        stripe_ready = bool(stripe_account and stripe_account.is_ready)

    # LOCKED: Free digital giveaways cap (SiteConfig-managed)
    free_digital_cap = 0
    free_digital_active_free_count = 0
    free_digital_remaining = 0
    can_use_free_digital_cap = False
    allow_new_listing = True

    if not is_owner_user(request.user):
        from core.config import get_site_config

        cfg = get_site_config()
        try:
            free_digital_cap = int(getattr(cfg, "free_digital_listing_cap", 5) or 5)
        except Exception:
            free_digital_cap = 5

        free_digital_active_free_count = Product.objects.filter(
            seller=request.user,
            kind=Product.Kind.FILE,
            is_active=True,
            is_free=True,
        ).count()

        free_digital_remaining = max(int(free_digital_cap) - int(free_digital_active_free_count), 0)
        can_use_free_digital_cap = free_digital_remaining > 0
        allow_new_listing = bool(stripe_ready or can_use_free_digital_cap)
    else:
        # Owner/admin bypass
        free_digital_cap = 5
        allow_new_listing = True

    products = list(qs)
    for p in products:
        p._publish_ok, p._publish_missing = _publish_checklist(p)

    return render(
        request,
        "products/seller/product_list.html",
        {
            "products": products,
            "q": q,
            "file_type": file_type,
            "file_type_options": _file_type_options(),
            "stripe_account": stripe_account,
            "stripe_ready": stripe_ready,
            "free_digital_cap": free_digital_cap,
            "free_digital_active_free_count": free_digital_active_free_count,
            "free_digital_remaining": free_digital_remaining,
            "can_use_free_digital_cap": can_use_free_digital_cap,
            "allow_new_listing": allow_new_listing,
        },
    )


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_create(request, *args, **kwargs):
    """
    Draft-first create: always starts inactive.
    """

    # LOCKED: If Stripe onboarding is not complete, restrict creating new
    # listings once the seller has reached the active FREE digital FILE cap.
    # (The owner/admin bypasses all seller restrictions.)
    if not is_owner_user(request.user):
        stripe_account = SellerStripeAccount.objects.filter(user=request.user).first()
        stripe_ready = bool(stripe_account and stripe_account.is_ready)
        if not stripe_ready:
            from core.config import get_site_config

            cfg = get_site_config()
            try:
                cap = int(getattr(cfg, "free_digital_listing_cap", 5) or 5)
            except Exception:
                cap = 5

            active_free_count = Product.objects.filter(
                seller=request.user,
                kind=Product.Kind.FILE,
                is_active=True,
                is_free=True,
            ).count()

            if active_free_count >= cap:
                messages.warning(
                    request,
                    f"You’ve reached the limit of {cap} active FREE file listings until Stripe onboarding is complete. "
                    "Finish Stripe setup to create more listings.",
                )
                return redirect("payments:connect_status")

    if request.method == "POST":
        form = ProductForm(request.POST, user=request.user)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.is_active = False

            # Slug behavior: if blank, auto generate from title
            if not (product.slug or "").strip():
                product.slug_is_manual = False
                product.slug = ""

            product.full_clean()
            product.save()
            messages.success(request, "Draft created. Complete images/specs/files, then activate from My Listings.")
            return redirect("products:seller_list")
    else:
        form = ProductForm(user=request.user)

    return render(request, "products/seller/product_form.html", {"form": form, "mode": "create"})


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_edit(request, pk: int, *args, **kwargs):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            # If slug isn't manual, keep it derived from title
            if not getattr(obj, "slug_is_manual", False):
                obj.slug = slugify(obj.title or "")
            obj.full_clean()
            obj.save()
            messages.success(request, f"Listing saved for '{product.title}'.")
            return redirect("products:seller_list")
    else:
        form = ProductForm(instance=product, user=request.user)

    return render(request, "products/seller/product_form.html", {"form": form, "mode": "edit", "product": product})


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_specs(request, pk: int):
    """
    Edit product specifications (different forms for MODEL vs FILE).
    """
    product = _get_owned_product_or_404(request, pk)

    if product.kind == Product.Kind.MODEL:
        from .models import ProductPhysical

        physical, _ = ProductPhysical.objects.get_or_create(product=product)
        if request.method == "POST":
            form = ProductPhysicalForm(request.POST, instance=physical)
            if form.is_valid():
                form.save()
                messages.success(request, f"Specs saved for '{product.title}' (physical).")
                return redirect("products:seller_list")
        else:
            form = ProductPhysicalForm(instance=physical)

        return render(request, "products/seller/product_specs_form.html", {"form": form, "product": product, "kind": "MODEL"})

    if product.kind == Product.Kind.FILE:
        from .models import ProductDigital

        digital, _ = ProductDigital.objects.get_or_create(product=product)
        if request.method == "POST":
            form = ProductDigitalForm(request.POST, instance=digital)
            if form.is_valid():
                form.save()
                messages.success(request, f"Specs saved for '{product.title}' (digital).")
                return redirect("products:seller_list")
        else:
            form = ProductDigitalForm(instance=digital)

        return render(request, "products/seller/product_specs_form.html", {"form": form, "product": product, "kind": "FILE"})

    messages.warning(request, "Product kind not recognized.")
    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_images(request, pk: int):
    """
    Image upload/manage page.

    LOCKED UX:
    - After saving an image, remain on the image upload page (so seller can keep uploading).
    """
    product = _get_owned_product_or_404(request, pk)

    def _next_sort_order() -> int:
        last = product.images.order_by("-sort_order", "-id").first()
        if not last:
            return 0
        try:
            return int(last.sort_order or 0) + 1
        except Exception:
            return product.images.count()

    bulk_form = ProductImageBulkUploadForm()

    if request.method == "POST":
        form = ProductImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                img: ProductImage = form.save(commit=False)
                img.product = product
                if img.sort_order is None:
                    img.sort_order = _next_sort_order()
                img.full_clean()
                img.save()

                # Primary enforcement: if uploaded as primary, clear others.
                if img.is_primary:
                    ProductImage.objects.filter(product=product).exclude(pk=img.pk).update(is_primary=False)

                # If no primary exists, set the earliest image as primary.
                if not ProductImage.objects.filter(product=product, is_primary=True).exists():
                    img.is_primary = True
                    img.save(update_fields=["is_primary"])

            messages.success(request, f"Image uploaded for '{product.title}'.")
            return redirect("products:seller_images", pk=product.pk)
        messages.error(request, "Please correct the upload errors below.")
    else:
        form = ProductImageUploadForm()

    images = product.images.all().order_by("sort_order", "id")
    return render(
        request,
        "products/seller/product_images.html",
        {"product": product, "form": form, "bulk_form": bulk_form, "images": images},
    )


@seller_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_images_bulk(request, pk: int):
    """
    Bulk upload multiple images (stays on images page).
    """
    product = _get_owned_product_or_404(request, pk)

    if request.method != "POST":
        return redirect("products:seller_images", pk=product.pk)

    form = ProductImageBulkUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Please correct the bulk upload errors.")
        return redirect("products:seller_images", pk=product.pk)

    files = request.FILES.getlist("images")
    if not files:
        messages.info(request, "No images selected.")
        return redirect("products:seller_images", pk=product.pk)

    created_count = 0
    with transaction.atomic():
        last = product.images.order_by("-sort_order", "-id").first()
        sort_order = int(last.sort_order) + 1 if last and last.sort_order is not None else product.images.count()

        for f in files:
            img = ProductImage(product=product, image=f, sort_order=sort_order)
            img.full_clean()
            img.save()
            created_count += 1
            sort_order += 1

        if created_count and not product.images.filter(is_primary=True).exists():
            first = product.images.order_by("sort_order", "id").first()
            if first:
                first.is_primary = True
                first.save(update_fields=["is_primary"])

    messages.success(request, f"Uploaded {created_count} image(s) for '{product.title}'.")
    return redirect("products:seller_images", pk=product.pk)


# ✅ RESTORED (your URLs import this)
@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_image_delete(request, pk: int, image_id: int):
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)

    if request.method == "POST":
        img.delete()
        messages.success(request, f"Image deleted for '{product.title}'.")
    return redirect("products:seller_images", pk=product.pk)


# ✅ RESTORED (your URLs import this)
@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_image_update(request, pk: int, image_id: int):
    """
    Update image properties (primary flag, sort order).
    """
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)

    if request.method != "POST":
        return redirect("products:seller_images", pk=product.pk)

    updated_fields: list[str] = []

    make_primary = (request.POST.get("make_primary") or "").strip()
    if make_primary == "1":
        ProductImage.objects.filter(product=product).exclude(pk=img.pk).update(is_primary=False)
        if not img.is_primary:
            img.is_primary = True
            updated_fields.append("is_primary")

    sort_order_raw = (request.POST.get("sort_order") or "").strip()
    if sort_order_raw:
        try:
            sort_val = int(sort_order_raw)
            if img.sort_order != sort_val:
                img.sort_order = sort_val
                updated_fields.append("sort_order")
        except Exception:
            messages.warning(request, "Sort order must be a number.")

    if updated_fields:
        img.full_clean()
        img.save(update_fields=updated_fields)
        messages.success(request, "Image updated.")
    else:
        messages.info(request, "No changes to save.")

    return redirect("products:seller_images", pk=product.pk)


@seller_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_assets(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if product.kind != Product.Kind.FILE:
        messages.info(request, "Assets are only for FILE listings.")
        return redirect("products:seller_list")

    if request.method == "POST":
        form = DigitalAssetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            asset: DigitalAsset = form.save(commit=False)
            asset.product = product
            asset.full_clean()
            asset.save()
            messages.success(request, f"Digital asset uploaded for '{product.title}'.")
            return redirect("products:seller_assets", pk=product.pk)
    else:
        form = DigitalAssetUploadForm()

    assets = product.digital_assets.all().order_by("id")
    return render(request, "products/seller/product_assets.html", {"product": product, "form": form, "assets": assets})


@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_asset_delete(request, pk: int, asset_id: int):
    product = _get_owned_product_or_404(request, pk)
    asset = get_object_or_404(DigitalAsset, pk=asset_id, product=product)
    if request.method == "POST":
        asset.delete()
        messages.success(request, f"Digital asset deleted for '{product.title}'.")
    return redirect("products:seller_assets", pk=product.pk)


@seller_required
def seller_product_preview(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    return _render_product_detail(request=request, product=product, log_event=False)


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_toggle_active(request, pk: int):
    """
    LOCKED:
    - Deactivate always allowed.
    - Activate blocked unless listing is complete (soft warnings + hard gate).
    - Activate for free digital FILE listings is allowed for non-Stripe-ready sellers only up to SiteConfig cap (default 5).
    """
    from core.config import get_site_config

    product = _get_owned_product_or_404(request, pk)

    if request.method != "POST":
        return redirect("products:seller_list")

    # Deactivate is always allowed
    if product.is_active:
        product.is_active = False
        product.save(update_fields=["is_active"])
        messages.success(request, f"Listing '{product.title}' is now inactive (draft).")
        return redirect("products:seller_list")

    # Checklist gate (must be complete)
    ok, missing = _publish_checklist(product)
    if not ok:
        messages.warning(
            request,
            "This listing can't be made active yet. Please complete: " + ", ".join(missing) + ".",
        )
        return redirect("products:seller_list")

    # Stripe readiness + free-cap gate (LOCKED behavior)
    stripe_ready = True
    if not is_owner_user(request.user):
        stripe_account = SellerStripeAccount.objects.filter(user=request.user).first()
        stripe_ready = bool(stripe_account and stripe_account.is_ready)

    # If not Stripe-ready, only allow up to N active FREE digital FILE listings
    if (not stripe_ready) and product.kind == Product.Kind.FILE and bool(product.is_free):
        cfg = get_site_config()
        try:
            cap = int(getattr(cfg, "free_digital_listing_cap", 5) or 5)
        except Exception:
            cap = 5

        active_free_count = (
            Product.objects.filter(
                seller=request.user,
                kind=Product.Kind.FILE,
                is_active=True,
                is_free=True,
            )
            .exclude(pk=product.pk)
            .count()
        )

        if active_free_count >= cap:
            messages.warning(
                request,
                f"You can only have {cap} active FREE file listings until Stripe onboarding is complete. "
                "Finish Stripe setup to activate more.",
            )
            return redirect("payments:connect_status")

    product.is_active = True
    product.save(update_fields=["is_active"])
    messages.success(request, f"Listing '{product.title}' is now active.")
    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_delete(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    if request.method == "POST":
        title = product.title
        product.delete()
        messages.success(request, f"Product '{title}' has been deleted.")
    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_duplicate(request, pk: int):
    """
    Duplicate product as a draft listing (copies images/assets if possible).
    """
    original = _get_owned_product_or_404(request, pk)

    # LOCKED: If Stripe onboarding is not complete, restrict creating new
    # listings once the seller has reached the active FREE digital FILE cap.
    if not is_owner_user(request.user):
        stripe_account = SellerStripeAccount.objects.filter(user=request.user).first()
        stripe_ready = bool(stripe_account and stripe_account.is_ready)
        if not stripe_ready:
            from core.config import get_site_config

            cfg = get_site_config()
            try:
                cap = int(getattr(cfg, "free_digital_listing_cap", 5) or 5)
            except Exception:
                cap = 5

            active_free_count = Product.objects.filter(
                seller=request.user,
                kind=Product.Kind.FILE,
                is_active=True,
                is_free=True,
            ).count()

            if active_free_count >= cap:
                messages.warning(
                    request,
                    f"You’ve reached the limit of {cap} active FREE file listings until Stripe onboarding is complete. "
                    "Finish Stripe setup to create more listings.",
                )
                return redirect("payments:connect_status")

    if request.method != "POST":
        return redirect("products:seller_list")

    with transaction.atomic():
        new_product = Product(
            seller=request.user,
            kind=original.kind,
            title=f"{original.title} (Copy)",
            slug="",
            slug_is_manual=False,
            short_description=original.short_description,
            description=original.description,
            category=original.category,
            subcategory=original.subcategory,
            price=original.price,
            is_free=original.is_free,
            is_active=False,
            complexity_level=getattr(original, "complexity_level", None),
            print_time_hours=getattr(original, "print_time_hours", None),
            max_purchases_per_buyer=getattr(original, "max_purchases_per_buyer", None),
            is_featured=False,
            is_trending=False,
        )
        new_product.slug_is_manual = False
        new_product.slug = ""
        new_product.full_clean()
        new_product.save()

        for img in original.images.all().order_by("sort_order", "id"):
            new_name = _safe_storage_copy(source_field=img.image, dest_prefix="product_images")
            if not new_name:
                continue
            ProductImage.objects.create(
                product=new_product,
                image=new_name,
                alt_text=img.alt_text,
                is_primary=img.is_primary,
                sort_order=img.sort_order,
            )

        if new_product.images.exists() and not new_product.images.filter(is_primary=True).exists():
            first = new_product.images.order_by("sort_order", "id").first()
            if first:
                first.is_primary = True
                first.save(update_fields=["is_primary"])

        if new_product.kind == Product.Kind.FILE:
            for asset in original.digital_assets.all().order_by("id"):
                new_asset_name = _safe_storage_copy(source_field=asset.file, dest_prefix="digital_assets")
                if not new_asset_name:
                    continue
                DigitalAsset.objects.create(
                    product=new_product,
                    file=new_asset_name,
                    file_type=asset.file_type,
                    original_filename=asset.original_filename,
                    file_size=asset.file_size,
                    sha256=getattr(asset, "sha256", ""),
                    zip_contents=getattr(asset, "zip_contents", {}),
                )

    messages.success(request, "Product duplicated as a draft. Edit images/files/specs from My Listings.")
    return redirect("products:seller_list")

@seller_required
@throttle(SELLER_CATEGORY_AJAX_RULE)
def seller_subcategories_for_category(request, *args, **kwargs):
    """
    URL target used by products/urls.py:

    path("seller/subcategories/", views_seller.seller_subcategories_for_category, name="seller_subcategories_for_category")

    Dependent dropdown helper:
    GET ?parent=<category_id>
    Returns: {"results": [{"id": <id>, "text": "<name>"}]}
    """
    category_id = request.GET.get("parent") or request.GET.get("category_id")
    try:
        category_id = int(category_id)
    except Exception:
        return JsonResponse({"results": []})

    parent = Category.objects.filter(pk=category_id).only("id", "type").first()
    if not parent:
        return JsonResponse({"results": []})

    qs = (
        Category.objects.filter(parent_id=parent.id, is_active=True, type=parent.type)
        .only("id", "name")
        .order_by("sort_order", "name")
    )
    return JsonResponse({"results": [{"id": c.id, "text": c.name} for c in qs]})