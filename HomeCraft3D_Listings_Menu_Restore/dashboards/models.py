# dashboards/models.py
from django.db import models
from django.conf import settings
from products.models import Product


class ProductFreeUnlock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="free_unlocks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="free_unlocked_products")
    created_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="free_unlocks_granted")
    
    class Meta:
        unique_together = ("product", "user")
        verbose_name = "Free Product Unlock"
        verbose_name_plural = "Free Product Unlocks"

    def __str__(self):
        return f"{self.user} unlocked {self.product}"
