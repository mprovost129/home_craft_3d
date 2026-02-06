# products/views_seller.py
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from django.contrib import messages
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from core.throttle import ThrottleRule, throttle
from payments.models import SellerStripeAccount
from .forms import ProductForm, ProductImageUploadForm, ProductImageBulkUploadForm, DigitalAssetUploadForm, ProductPhysicalForm, ProductDigitalForm
from .models import Product, ProductImage, DigitalAsset, ALLOWED_ASSET_EXTS
from .permissions import seller_required, is_owner_user
from .views import _render_product_detail


SELLER_PRODUCT_MUTATE_RULE = ThrottleRule(key_prefix="seller_product_mutate", limit=20, window_seconds=60)
SELLER_UPLOAD_RULE = ThrottleRule(key_prefix="seller_upload", limit=12, window_seconds=60)
SELLER_DELETE_RULE = ThrottleRule(key_prefix="seller_delete", limit=20, window_seconds=60)


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


def _safe_storage_copy(*, source_field, dest_prefix: str) -> Optional[str]:
    """
    Copy a stored file to a new key/path and return the new name.

    - If using django-storages S3Boto3Storage, try *server-side* bucket copy (fast).
    - Otherwise fall back to reading + saving (streaming via File wrapper).
    """
    if not source_field:
        return None

    storage = getattr(source_field, "storage", None)
    name = getattr(source_field, "name", None)
    if not storage or not name:
        return None

    ext = Path(name).suffix
    new_name = f"{dest_prefix}/{uuid.uuid4().hex}{ext}"

    # Attempt S3 server-side copy if the storage exposes bucket + connection.
    bucket = getattr(storage, "bucket", None)
    location = (getattr(storage, "location", "") or "").strip("/")

    if bucket is not None:
        # Build a CopySource that matches the actual object key.
        src_key = f"{location}/{name}".lstrip("/") if location else name
        try:
            bucket.copy(
                {"Bucket": bucket.name, "Key": src_key},
                f"{location}/{new_name}".lstrip("/") if location else new_name,
            )
            return new_name
        except Exception:
            # Fall through to stream copy.
            pass

    # Fallback: open and re-save (can be slower for large files, but safe).
    try:
        source_field.open("rb")
        storage.save(new_name, File(source_field))
        return new_name
    except Exception:
        return None
    finally:
        try:
            source_field.close()
        except Exception:
            pass


@seller_required
def seller_product_list(request, *args, **kwargs):
    """
    Seller dashboard: list your products.
    Owner/admin sees all products.

    NOTE: This is NOT gated by Stripe readiness. Sellers can still create drafts pre-onboarding.
    """
    qs = (
        Product.objects.select_related("category", "category__parent", "seller", "digital", "physical")
        .prefetch_related("images", "digital_assets")
        .order_by("-created_at")
    )
    if not is_owner_user(request.user):
        qs = qs.filter(seller=request.user)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(short_description__icontains=q) | Q(description__icontains=q))

    file_type = (request.GET.get("file_type") or "").strip().lower().lstrip(".")
    if file_type:
        qs = qs.filter(
            Q(digital_assets__file_type=file_type)
            | Q(digital_assets__file__iendswith=f".{file_type}")
        ).distinct()

    stripe_account = None
    stripe_ready = True
    if not is_owner_user(request.user):
        stripe_account = SellerStripeAccount.objects.filter(user=request.user).first()
        stripe_ready = bool(stripe_account and stripe_account.is_ready)

    return render(
        request,
        "products/seller/product_list.html",
        {
            "products": qs,
            "q": q,
            "file_type": file_type,
            "file_type_options": _file_type_options(),
            "stripe_account": stripe_account,
            "stripe_ready": stripe_ready,
        },
    )


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_create(request, *args, **kwargs):
    """
    Draft-first create:
    - Create listing with is_active=False by default.
    - Redirect flow:
        FILE -> Assets page first
        MODEL -> Images page first
    """
    if request.method == "POST":
        form = ProductForm(request.POST, user=request.user)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user

            # Draft-first
            product.is_active = False

            # Generate slug before validation if not provided
            if not product.slug:
                product.slug = slugify(product.title)[:180]

            product.full_clean()
            product.save()

            if product.kind == Product.Kind.FILE:
                messages.success(
                    request,
                    f"Draft created for '{product.title}' (digital file listing). Add files and images from My Listings.",
                )
            else:
                messages.success(
                    request,
                    f"Draft created for '{product.title}' (physical listing). Add images and specs from My Listings.",
                )
            return redirect("products:seller_list")
    else:
        form = ProductForm(user=request.user)

    return render(request, "products/seller/product_form.html", {"form": form, "mode": "create"})


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_edit(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)

            # Keep existing slug if blank on form submission
            if not obj.slug:
                obj.slug = slugify(obj.title)[:180]

            obj.full_clean()
            obj.save()
            messages.success(request, f"Listing saved for '{product.title}'.")
            return redirect("products:seller_list")
    else:
        form = ProductForm(instance=product, user=request.user)

    return render(
        request,
        "products/seller/product_form.html",
        {"form": form, "mode": "edit", "product": product},
    )


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_specs(request, pk: int):
    """Edit product specifications (different forms for MODEL vs FILE)."""
    product = _get_owned_product_or_404(request, pk)
    
    if product.kind == Product.Kind.MODEL:
        # Get or create ProductPhysical
        from .models import ProductPhysical
        physical, created = ProductPhysical.objects.get_or_create(product=product)
        
        if request.method == "POST":
            form = ProductPhysicalForm(request.POST, instance=physical)
            if form.is_valid():
                form.save()
                messages.success(request, f"Specs saved for '{product.title}' (physical).")
                return redirect("products:seller_list")
        else:
            form = ProductPhysicalForm(instance=physical)
        
        return render(
            request,
            "products/seller/product_specs_form.html",
            {"form": form, "product": product, "kind": "MODEL"},
        )
    
    elif product.kind == Product.Kind.FILE:
        # Get or create ProductDigital
        from .models import ProductDigital
        digital, created = ProductDigital.objects.get_or_create(product=product)
        
        if request.method == "POST":
            form = ProductDigitalForm(request.POST, instance=digital)
            if form.is_valid():
                form.save()
                messages.success(request, f"Specs saved for '{product.title}' (digital file).")
                return redirect("products:seller_list")
        else:
            form = ProductDigitalForm(instance=digital)
        
        return render(
            request,
            "products/seller/product_specs_form.html",
            {"form": form, "product": product, "kind": "FILE"},
        )
    
    else:
        messages.warning(request, "Product kind not recognized.")
        return redirect("products:seller_list")


@seller_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_images(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    def _next_sort_order() -> int:
        last = product.images.order_by("-sort_order", "-id").first()
        if not last:
            return 0
        try:
            return int(last.sort_order) + 1
        except Exception:
            return product.images.count()

    if request.method == "POST":
        form = ProductImageUploadForm(request.POST, request.FILES)

        if form.is_valid():
            with transaction.atomic():
                img: ProductImage = form.save(commit=False)
                img.product = product

                # Default sort_order if user left it blank
                if img.sort_order is None:
                    img.sort_order = _next_sort_order()

                img.full_clean()
                img.save()

                if img.is_primary:
                    ProductImage.objects.filter(product=product).exclude(pk=img.pk).update(is_primary=False)

                # If no primary exists, make this one primary
                if not ProductImage.objects.filter(product=product, is_primary=True).exists():
                    img.is_primary = True
                    img.save(update_fields=["is_primary"])

                messages.success(request, f"Image uploaded for '{product.title}'.")
                return redirect("products:seller_list")
    else:
        form = ProductImageUploadForm()
        bulk_form = ProductImageBulkUploadForm()

    images = product.images.all().order_by("sort_order", "id")
    return render(
        request,
        "products/seller/product_images.html",
        {"product": product, "form": form, "images": images},
    )


@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_image_delete(request, *args, **kwargs):
    pk = kwargs.get("pk")
    image_id = kwargs.get("image_id")
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)

    if request.method == "POST":
        was_primary = img.is_primary
        img.delete()
        if was_primary:
            next_img = ProductImage.objects.filter(product=product).order_by("sort_order", "id").first()
            if next_img:
                next_img.is_primary = True
                next_img.save(update_fields=["is_primary"])
        messages.success(request, f"Image deleted for '{product.title}'.")
        return redirect("products:seller_list")

    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_image_update(request, pk: int, image_id: int):
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)

    if request.method != "POST":
        return redirect("products:seller_images", pk=product.pk)

    action = (request.POST.get("action") or "").strip()
    sort_value = (request.POST.get("sort_order") or "").strip()

    updated_fields = []

    if sort_value:
        try:
            sort_order = int(sort_value)
            if sort_order < 0:
                sort_order = 0
            if img.sort_order != sort_order:
                img.sort_order = sort_order
                updated_fields.append("sort_order")
        except ValueError:
            messages.error(request, "Sort order must be a whole number.")

    if action == "make_primary":
        ProductImage.objects.filter(product=product).exclude(pk=img.pk).update(is_primary=False)
        if not img.is_primary:
            img.is_primary = True
            updated_fields.append("is_primary")

    if updated_fields:
        img.save(update_fields=updated_fields)
        if action == "make_primary":
            messages.success(request, f"Primary image updated for '{product.title}'.")
        elif "sort_order" in updated_fields:
            messages.success(request, f"Image order updated for '{product.title}'.")
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
            return redirect("products:seller_list")
    else:
        form = DigitalAssetUploadForm()

    assets = product.digital_assets.all().order_by("id")
    return render(
        request,
        "products/seller/product_assets.html",
        {"product": product, "form": form, "assets": assets},
    )


@seller_required
def seller_product_preview(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    return _render_product_detail(request=request, product=product, log_event=False)


@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_asset_delete(request, *args, **kwargs):
    pk = kwargs.get("pk")
    asset_id = kwargs.get("asset_id")
    product = _get_owned_product_or_404(request, pk)
    asset = get_object_or_404(DigitalAsset, pk=asset_id, product=product)

    if request.method == "POST":
        asset.delete()
        messages.success(request, f"Digital asset deleted for '{product.title}'.")
        return redirect("products:seller_list")

    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_toggle_active(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    if request.method == "POST":
        product.is_active = not product.is_active
        product.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Listing '{product.title}' is now {'active' if product.is_active else 'inactive (draft)'}.",
        )
    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_DELETE_RULE)
def seller_product_delete(request, pk: int):
    """
    Delete a product listing.
    Note: This will cascade delete related images, assets, specs, etc.
    """
    product = _get_owned_product_or_404(request, pk)
    
    if request.method == "POST":
        product_title = product.title
        product.delete()
        messages.success(request, f"Product '{product_title}' has been deleted.")
        return redirect("products:seller_list")
    
    return redirect("products:seller_list")


@seller_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_duplicate(request, pk: int):
    """
    Create a copy of a product with the same details but as a new listing (draft).

    IMPORTANT:
    - This performs a SAFE copy of file blobs:
      - On S3 (django-storages), attempts server-side copy (fast).
      - Otherwise falls back to open()+save().

    - The duplicate starts as inactive (draft).
    """
    original = _get_owned_product_or_404(request, pk)

    if request.method != "POST":
        return redirect("products:seller_list")

    with transaction.atomic():
        new_product = Product(
            seller=request.user,
            kind=original.kind,
            title=f"{original.title} (Copy)",
            slug="",  # will be set below
            short_description=original.short_description,
            description=original.description,
            category=original.category,
            price=original.price,
            is_free=original.is_free,
            is_active=False,  # draft
            complexity_level=original.complexity_level,
            print_time_hours=original.print_time_hours,
        )

        base_slug = slugify(f"{original.slug}-copy")[:180] or f"{original.pk}-copy"
        candidate = base_slug
        counter = 1
        while Product.objects.filter(seller=request.user, slug=candidate).exists():
            candidate = slugify(f"{base_slug}-{counter}")[:180]
            counter += 1
        new_product.slug = candidate

        new_product.full_clean()
        new_product.save()

        # Copy images (safe storage copy)
        for img in original.images.all().order_by("sort_order", "id"):
            new_name = _safe_storage_copy(source_field=img.image, dest_prefix="product_images")
            if not new_name:
                # If copy fails, skip rather than breaking the whole duplicate.
                continue
            ProductImage.objects.create(
                product=new_product,
                image=new_name,  # storage path
                alt_text=img.alt_text,
                is_primary=img.is_primary,
                sort_order=img.sort_order,
            )

        # Ensure exactly one primary if any images exist
        if new_product.images.exists() and not new_product.images.filter(is_primary=True).exists():
            first = new_product.images.order_by("sort_order", "id").first()
            if first:
                first.is_primary = True
                first.save(update_fields=["is_primary"])

        # Copy digital assets if applicable (safe storage copy)
        if original.kind == Product.Kind.FILE:
            for asset in original.digital_assets.all().order_by("id"):
                new_asset_name = _safe_storage_copy(source_field=asset.file, dest_prefix="digital_assets")
                if not new_asset_name:
                    continue
                DigitalAsset.objects.create(
                    product=new_product,
                    file=new_asset_name,
                    original_filename=asset.original_filename,
                    file_type=asset.file_type,
                    zip_contents=asset.zip_contents,
                )

    messages.success(
        request,
        "Product duplicated as a draft. Edit files, images, and specs from My Listings.",
    )
    return redirect("products:seller_list")
