from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category


CATEGORY_TREE = [
    {
        "name": "Automotive",
        "children": [
            "Interior",
            "Exterior",
            "Tools",
            "Accessories",
        ],
    },
    {
        "name": "Educational",
        "children": [
            "STEM",
            "Learning Aids",
            "Models",
        ],
    },
    {
        "name": "Figurines",
        "children": [
            "Fantasy",
            "Sci-Fi",
            "Animals",
            "People",
        ],
    },
    {
        "name": "Games & Toys",
        "children": [
            "Board Games",
            "Tabletop",
            "Puzzles",
            "Toys",
        ],
    },
    {
        "name": "Home & Decor",
        "children": [
            "Wall Art",
            "Lighting",
            "Furniture",
            "Kitchen",
        ],
    },
    {
        "name": "Miniatures",
        "children": [
            "Scale Models",
            "Architecture",
            "Vehicles",
        ],
    },
    {
        "name": "Organizers",
        "children": [
            "Office",
            "Garage",
            "Workshop",
            "Storage",
        ],
    },
    {
        "name": "Props & Cosplay",
        "children": [
            "Armor",
            "Weapons",
            "Accessories",
        ],
    },
    {
        "name": "Terrain & Diorama",
        "children": [
            "Buildings",
            "Landscape",
            "Scatter",
        ],
    },
    {
        "name": "Tools & Fixtures",
        "children": [
            "Jigs",
            "Holders",
            "Calibration",
        ],
    },
    {
        "name": "Art & Sculptures",
        "children": [
            "Abstract",
            "Busts",
            "Relief",
        ],
    },
    {
        "name": "Bundles",
        "children": [],
    },
]


class Command(BaseCommand):
    help = "Seed symmetric category trees for MODEL and FILE products."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding categories…")

        for category_type, label in [
            (Category.CategoryType.MODEL, "3D Models"),
            (Category.CategoryType.FILE, "3D Files"),
        ]:
            self.stdout.write(f"  → {label}")

            for sort_index, root_def in enumerate(CATEGORY_TREE):
                root, root_created = Category.objects.get_or_create(
                    type=category_type,
                    parent=None,
                    slug=root_def["name"].lower().replace(" ", "-"),
                    defaults={
                        "name": root_def["name"],
                        "sort_order": sort_index,
                        "is_active": True,
                    },
                )

                if not root_created:
                    root.name = root_def["name"]
                    root.sort_order = sort_index
                    root.is_active = True
                    root.save(update_fields=["name", "sort_order", "is_active"])

                for child_index, child_name in enumerate(root_def.get("children", [])):
                    child, child_created = Category.objects.get_or_create(
                        type=category_type,
                        parent=root,
                        slug=child_name.lower().replace(" ", "-"),
                        defaults={
                            "name": child_name,
                            "sort_order": child_index,
                            "is_active": True,
                        },
                    )

                    if not child_created:
                        child.name = child_name
                        child.sort_order = child_index
                        child.is_active = True
                        child.save(update_fields=["name", "sort_order", "is_active"])

        self.stdout.write(self.style.SUCCESS("✔ Categories seeded successfully"))
