# legal/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import LegalAcceptance, LegalDocument


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "version", "title", "is_published", "created_at")
    list_filter = ("doc_type", "is_published", "created_at")
    search_fields = ("title", "body")
    ordering = ("doc_type", "-version")
    readonly_fields = ("created_at",)

    actions = [
        "publish_selected",
        "publish_selected_unpublish_others",
        "clone_as_next_version",
    ]

    @admin.action(description="Publish selected documents (does NOT unpublish others)")
    def publish_selected(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"Published {updated} document(s).", level=messages.SUCCESS)

    @admin.action(description="Publish selected (unpublish other published versions of same doc_type)")
    def publish_selected_unpublish_others(self, request, queryset):
        """
        For each selected LegalDocument:
          - unpublish all OTHER docs of the same doc_type
          - publish this doc
        This ensures there is only one published version per doc_type (for the ones you select).
        """
        docs = list(queryset.select_related(None))
        if not docs:
            self.message_user(request, "No documents selected.", level=messages.WARNING)
            return

        # We do it doc-by-doc so selecting multiple doc_types works.
        # If you select multiple versions of the SAME doc_type, the highest version wins.
        docs_by_type: dict[str, LegalDocument] = {}
        for d in docs:
            current = docs_by_type.get(d.doc_type)
            if current is None or d.version > current.version:
                docs_by_type[d.doc_type] = d

        published_count = 0
        with transaction.atomic():
            for doc_type, chosen in docs_by_type.items():
                # Unpublish all others of this type
                LegalDocument.objects.filter(doc_type=doc_type, is_published=True).exclude(pk=chosen.pk).update(
                    is_published=False
                )
                # Publish the chosen one
                if not chosen.is_published:
                    LegalDocument.objects.filter(pk=chosen.pk).update(is_published=True)
                    published_count += 1
                else:
                    # Still count it as "ensured published"
                    published_count += 1

        if len(docs) != len(docs_by_type):
            self.message_user(
                request,
                "Note: You selected multiple versions for at least one doc type; "
                "the highest version per doc type was published.",
                level=messages.WARNING,
            )

        self.message_user(
            request,
            f"Published {published_count} doc type(s) and unpublished previous published versions for those types.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Clone selected as next version (draft, not published)")
    def clone_as_next_version(self, request, queryset):
        """
        Clones each selected doc into a new row:
          - same doc_type
          - version = max(version)+1 for that doc_type
          - is_published = False
          - created_at = now (auto)
        """
        docs = list(queryset)
        if not docs:
            self.message_user(request, "No documents selected.", level=messages.WARNING)
            return

        created = 0
        with transaction.atomic():
            for doc in docs:
                next_version = (
                    LegalDocument.objects.filter(doc_type=doc.doc_type).order_by("-version").values_list("version", flat=True).first()
                    or 0
                ) + 1

                LegalDocument.objects.create(
                    doc_type=doc.doc_type,
                    version=next_version,
                    title=doc.title,
                    body=doc.body,
                    is_published=False,
                )
                created += 1

        self.message_user(
            request,
            f"Cloned {created} document(s) as next-version drafts. "
            "Go to the list, edit as needed, then publish.",
            level=messages.SUCCESS,
        )


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("accepted_at", "document", "user", "guest_email", "ip_address")
    list_filter = ("document__doc_type", "accepted_at")
    search_fields = ("guest_email", "user__username", "user__email", "document_hash")
    readonly_fields = ("accepted_at", "document_hash", "ip_address", "user_agent")
    ordering = ("-accepted_at",)
