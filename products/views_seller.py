from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from core.throttle import ThrottleRule, throttle
from payments.models import SellerStripeAccount
from payments.decorators import stripe_ready_required
from .forms import ProductForm, ProductImageUploadForm, DigitalAssetUploadForm
from .models import Product, ProductImage, DigitalAsset, ALLOWED_ASSET_EXTS
from .permissions import seller_required, is_owner_user


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


@seller_required
def seller_product_list(request, *args, **kwargs):
    """
    Seller dashboard: list your products.
    Owner/admin sees all products.

    NOTE: This is NOT gated by Stripe readiness. Sellers can still view what they have.
    """
    qs = (
        Product.objects.select_related("category", "seller")
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
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_create(request, *args, **kwargs):
    if request.method == "POST":
        form = ProductForm(request.POST, user=request.user)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            # Generate slug before validation if not provided
            if not product.slug:
                product.slug = slugify(product.title)[:180]
            product.full_clean()
            product.save()
            messages.success(request, "Product created. Next: add images (and digital assets if applicable).")
            return redirect("products:seller_images", pk=product.pk)
    else:
        form = ProductForm(user=request.user)

    return render(request, "products/seller/product_form.html", {"form": form, "mode": "create"})


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_edit(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
            messages.success(request, "Product updated.")
            return redirect("products:seller_list")
    else:
        form = ProductForm(instance=product, user=request.user)

    return render(
        request,
        "products/seller/product_form.html",
        {"form": form, "mode": "edit", "product": product},
    )


@seller_required
@stripe_ready_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_images(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        form = ProductImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            img: ProductImage = form.save(commit=False)
            img.product = product
            img.full_clean()
            img.save()

            if img.is_primary:
                ProductImage.objects.filter(product=product).exclude(pk=img.pk).update(is_primary=False)

            messages.success(request, "Image uploaded.")
            return redirect("products:seller_images", pk=product.pk)
    else:
        form = ProductImageUploadForm()

    images = product.images.all().order_by("sort_order", "id")
    return render(
        request,
        "products/seller/product_images.html",
        {"product": product, "form": form, "images": images},
    )


@seller_required
@stripe_ready_required
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
        messages.success(request, "Image deleted.")
        return redirect("products:seller_images", pk=product.pk)

    return redirect("products:seller_images", pk=product.pk)


@seller_required
@stripe_ready_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_assets(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if product.kind != Product.Kind.FILE:
        messages.info(request, "This is not a digital file product. Assets are only for FILE listings.")
        return redirect("products:seller_list")

    if request.method == "POST":
        form = DigitalAssetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            asset: DigitalAsset = form.save(commit=False)
            asset.product = product
            asset.full_clean()
            asset.save()
            messages.success(request, "Digital asset uploaded.")
            return redirect("products:seller_assets", pk=product.pk)
    else:
        form = DigitalAssetUploadForm()

    assets = product.digital_assets.all().order_by("id")
    return render(
        request,
        "products/seller/product_assets.html",
        {"product": product, "form": form, "assets": assets},
    )


@seller_required
@stripe_ready_required
@throttle(SELLER_DELETE_RULE)
def seller_product_asset_delete(request, *args, **kwargs):
    pk = kwargs.get("pk")
    asset_id = kwargs.get("asset_id")
    product = _get_owned_product_or_404(request, pk)
    asset = get_object_or_404(DigitalAsset, pk=asset_id, product=product)

    if request.method == "POST":
        asset.delete()
        messages.success(request, "Digital asset deleted.")
        return redirect("products:seller_assets", pk=product.pk)

    return redirect("products:seller_assets", pk=product.pk)


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_toggle_active(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    if request.method == "POST":
        product.is_active = not product.is_active
        product.save(update_fields=["is_active"])
        messages.success(request, f"Listing is now {'active' if product.is_active else 'inactive'}.")
    return redirect("products:seller_list")
