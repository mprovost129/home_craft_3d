# reviews/models.py
from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """Buyer review for a purchased product."""

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.CASCADE,
        related_name="review",
        help_text="Enforces one review per purchased line item.",
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1–5 stars",
    )

    title = models.CharField(max_length=120, blank=True, default="")
    body = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["buyer", "created_at"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self) -> str:
        return f"Review<{self.product_id}> by {self.buyer_id} ({self.rating}/5)"


class ReviewReply(models.Model):
    """Seller reply to a product review.

    Locked spec: seller replies are allowed.
    We allow at most one reply per review (one-to-one).
    """

    review = models.OneToOneField(
        Review,
        on_delete=models.CASCADE,
        related_name="reply",
    )

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_replies",
    )

    body = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["seller", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"ReviewReply<review={self.review_id} seller={self.seller_id}>"


class SellerReview(models.Model):
    """Purchased-only rating for a seller.

    Rules:
    - Only an authenticated buyer (Order.buyer) can rate.
    - Order must be PAID.
    - Order must include at least one OrderItem for that seller.

    We bind to the Order itself (not a specific item) so a buyer can leave ONE
    seller rating per order for that seller.
    """

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_reviews_received",
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_reviews_written",
    )

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="seller_reviews",
    )

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1–5 stars",
    )

    title = models.CharField(max_length=120, blank=True, default="")
    body = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["buyer", "seller", "order"], name="uniq_seller_review_per_order"),
        ]
        indexes = [
            models.Index(fields=["seller", "created_at"]),
            models.Index(fields=["buyer", "created_at"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self) -> str:
        return f"SellerReview<seller={self.seller_id} buyer={self.buyer_id} order={self.order_id}> ({self.rating}/5)"