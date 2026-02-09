# core/models_email.py
from django.db import models

class SiteEmailTemplate(models.Model):
    site_config = models.ForeignKey(
        'core.SiteConfig',
        on_delete=models.CASCADE,
        related_name='email_templates',
        help_text='Site config this template belongs to.',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=100, unique=True, help_text="Template identifier (e.g. 'staff_announcement')")
    subject = models.CharField(max_length=200, help_text="Email subject line")
    body = models.TextField(help_text="Email body. You can use {{ user }}, {{ site_name }}, etc.")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Email Template"
        verbose_name_plural = "Site Email Templates"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"
