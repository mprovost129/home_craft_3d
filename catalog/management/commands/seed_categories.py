from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category


@dataclass(frozen=True)
class SeedNode:
    name: str
    children: list[str]


# ---------------------------------------------------------------------
# CATEGORY TREE (shared by MODEL + FILE)
# ---------------------------------------------------------------------
# NOTE:
# - These are "root categories" with subcategories.
# - They will be duplicated for type=MODEL and type=FILE.
# ---------------------------------------------------------------------
CATEGORY_TREE: list[SeedNode] = [
    SeedNode("Art & Sculptures", [
        "Statues & Figurative",
        "Busts",
        "Abstract Art",
        "Wall Art / Reliefs",
        "Mini Sculptures",
        "Masks",
        "Vases & Decor Sculptures",
        "Articulated Art Pieces",
    ]),
    SeedNode("Miniatures & Terrain", [
        "Dungeon / Tiles",
        "Buildings & Ruins",
        "Scatter Terrain",
        "Trees & Foliage",
        "Bases",
        "Vehicles (Mini Scale)",
        "Sci-Fi Terrain",
        "Fantasy Terrain",
        "Modern / Urban Terrain",
    ]),
    SeedNode("Tabletop Gaming", [
        "RPG Accessories",
        "Dice Towers",
        "Dice Trays",
        "Dice Vaults / Boxes",
        "Mini Holders / Stands",
        "Token Trays",
        "Card Holders",
        "Game Inserts / Organizers",
        "Terrain Accessories",
    ]),
    SeedNode("Cosplay & Props", [
        "Helmets",
        "Armor Pieces",
        "Weapons (Prop)",
        "Gadgets / Sci-Fi Props",
        "Masks",
        "Wearables / Accessories",
        "Emblems & Badges",
        "Display Stands",
        "Foam / Pepakura Helpers",
    ]),
    SeedNode("Jewelry & Accessories", [
        "Rings",
        "Earrings",
        "Pendants",
        "Bracelets",
        "Necklaces",
        "Charms",
        "Brooches / Pins",
        "Keychains",
    ]),
    SeedNode("Household & Organization", [
        "Kitchen Helpers",
        "Bathroom Accessories",
        "Cable Management",
        "Storage Bins",
        "Hooks & Hangers",
        "Closet Organizers",
        "Desk Organizers",
        "Tool Organization",
        "Labeling / Tags",
    ]),
    SeedNode("Tools & Workshop", [
        "Jigs & Fixtures",
        "Tool Holders",
        "Drill Guides",
        "Measuring Tools",
        "Clamps & Aids",
        "Sanding / Finishing Tools",
        "Shop Storage",
        "3D Printer Tools",
    ]),
    SeedNode("3D Printer Upgrades", [
        "Spool Holders",
        "Filament Guides",
        "Cable Chains",
        "Fan Ducts",
        "Toolhead Accessories",
        "Bed Leveling Tools",
        "Enclosure Parts",
        "Raspberry Pi / Camera Mounts",
    ]),
    SeedNode("Electronics & Tech", [
        "Raspberry Pi Cases",
        "Arduino / Microcontroller Cases",
        "Sensor Housings",
        "Cable Glands / Grommets",
        "Mounts & Brackets",
        "Phone Accessories",
        "Tablet / Laptop Stands",
        "Remote / Controller Holders",
    ]),
    SeedNode("Automotive", [
        "Interior Accessories",
        "Exterior Accessories",
        "Phone / Dash Mounts",
        "Organization / Storage",
        "Gauges / Panels",
        "Replacement Clips",
        "Cable / Wire Guides",
        "Key Fob Accessories",
    ]),
    SeedNode("Sports & Outdoors", [
        "Bike Accessories",
        "Camping Gear",
        "Hiking Accessories",
        "Fishing Accessories",
        "Fitness Accessories",
        "Water Bottle Holders",
        "Outdoor Hooks / Clips",
        "Gear Mounts",
    ]),
    SeedNode("Toys & Games", [
        "Educational Toys",
        "Puzzles",
        "Board Game Accessories",
        "Construction Toys",
        "Fidget Toys",
        "Marble Runs",
        "Toy Vehicles",
        "Play Sets",
    ]),
    SeedNode("Educational", [
        "STEM Models",
        "Science Demonstrations",
        "Math Aids",
        "Anatomy Models",
        "Geography / Maps",
        "Classroom Tools",
        "Engineering Models",
    ]),
    SeedNode("Robotics", [
        "Chassis & Frames",
        "Wheels & Tracks",
        "Servo Mounts",
        "Sensor Mounts",
        "Gearboxes",
        "Grippers",
        "Cable Management",
        "Controller Cases",
    ]),
    SeedNode("Home & Decor", [
        "Vases",
        "Planters",
        "Wall Hooks",
        "Decorative Signs",
        "Ornaments",
        "Photo Frames",
        "Lamp Shades",
        "Seasonal Decor",
    ]),
    SeedNode("Functional Parts", [
        "Brackets",
        "Clips",
        "Spacers / Shims",
        "Caps / Covers",
        "Knobs / Handles",
        "Hinges",
        "Adapters",
        "Replacement Parts",
    ]),
    SeedNode("Office & Desk", [
        "Pen Holders",
        "Document Trays",
        "Cable Organizers",
        "Monitor Stands",
        "Phone Stands",
        "Headphone Hangers",
        "Drawer Organizers",
        "Nameplates",
    ]),
    SeedNode("Photography & Video", [
        "Camera Mounts",
        "Tripod Accessories",
        "Light Modifiers",
        "GoPro / Action Cam Mounts",
        "Cable Management",
        "Battery Holders",
        "Lens Caps / Holders",
    ]),
    SeedNode("Music & Audio", [
        "Instrument Accessories",
        "Guitar Picks / Holders",
        "Headphone Stands",
        "Cable Winders",
        "Speaker Stands",
        "Microphone Mounts",
        "Pedalboard Accessories",
    ]),
    SeedNode("Pets", [
        "Food / Water Accessories",
        "Toys",
        "Leash / Collar Accessories",
        "Grooming Helpers",
        "Enclosures / Doors",
        "Pet Tags",
        "Storage / Organization",
    ]),
    SeedNode("Medical & Accessibility", [
        "Grip Aids",
        "Assistive Tools",
        "Pill Organizers",
        "Mobility Accessories",
        "Ergonomic Helpers",
        "Adaptive Mounts",
    ]),
    SeedNode("Hobby & RC", [
        "RC Car Parts",
        "Drone Accessories",
        "Plane / Boat Parts",
        "Battery Mounts",
        "Servo Mounts",
        "Camera Mounts",
        "Field Tools",
    ]),
    SeedNode("Garden", [
        "Plant Labels",
        "Planters",
        "Irrigation Helpers",
        "Tool Hooks",
        "Garden Decor",
        "Seed Starters",
    ]),
    SeedNode("Architecture & Models", [
        "Scale Buildings",
        "Terrain / Landscaping",
        "Model Details",
        "Presentation Bases",
        "Structural Mockups",
        "Site Models",
    ]),
    SeedNode("Holiday & Seasonal", [
        "Christmas",
        "Halloween",
        "Easter",
        "Thanksgiving",
        "Valentine’s Day",
        "Birthdays",
        "Wedding Decor",
    ]),
    SeedNode("Signs & Tags", [
        "Door Signs",
        "Desk Signs",
        "Nameplates",
        "Warning Labels",
        "QR / NFC Holders",
        "Custom Tags",
    ]),
    SeedNode("Stands & Displays", [
        "Model Stands",
        "Phone Stands",
        "Controller Stands",
        "Headphone Stands",
        "Retail Displays",
        "Wall Mount Displays",
        "Shelf Displays",
    ]),
    SeedNode("Bundles", [
        "Starter Packs",
        "Theme Packs",
        "Mega Bundles",
        "Creator Collections",
        "Seasonal Bundles",
    ]),
]


# ---------------------------------------------------------------------
# SEED HELPERS
# ---------------------------------------------------------------------
def _slug(name: str) -> str:
    s = slugify(name)[:140]
    return s or "category"


def _upsert_root(*, ctype: str, name: str, sort_order: int) -> Category:
    obj, _created = Category.objects.get_or_create(
        type=ctype,
        parent=None,
        slug=_slug(name),
        defaults={
            "name": name,
            "description": "",
            "is_active": True,
            "sort_order": sort_order,
        },
    )
    changed = False

    if obj.name != name:
        obj.name = name
        changed = True

    # Keep slug stable for idempotency (don’t rewrite unless empty)
    if not obj.slug:
        obj.slug = _slug(name)
        changed = True

    if obj.is_active is not True:
        obj.is_active = True
        changed = True

    if obj.sort_order != sort_order:
        obj.sort_order = sort_order
        changed = True

    if changed:
        obj.save(update_fields=["name", "slug", "is_active", "sort_order", "updated_at"])

    return obj


def _upsert_child(*, ctype: str, parent: Category, name: str, sort_order: int) -> Category:
    obj, _created = Category.objects.get_or_create(
        type=ctype,
        parent=parent,
        slug=_slug(name),
        defaults={
            "name": name,
            "description": "",
            "is_active": True,
            "sort_order": sort_order,
        },
    )
    changed = False

    if obj.name != name:
        obj.name = name
        changed = True

    if not obj.slug:
        obj.slug = _slug(name)
        changed = True

    if obj.is_active is not True:
        obj.is_active = True
        changed = True

    if obj.sort_order != sort_order:
        obj.sort_order = sort_order
        changed = True

    if changed:
        obj.save(update_fields=["name", "slug", "is_active", "sort_order", "updated_at"])

    return obj


class Command(BaseCommand):
    help = "Seed marketplace categories + subcategories for both MODEL and FILE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete ALL categories before seeding (use if you accidentally removed/duplicated categories).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without writing changes.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        wipe: bool = bool(options.get("wipe"))
        dry_run: bool = bool(options.get("dry_run"))

        if wipe:
            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN: would delete all Category rows."))
            else:
                Category.objects.all().delete()
                self.stdout.write(self.style.WARNING("Deleted all categories."))

        created_count = 0
        updated_count = 0
        # We track changes by counting objects before/after and re-fetching
        # (Django's get_or_create doesn't tell us about updates we apply).
        before_total = Category.objects.count()

        types: list[str] = [Category.CategoryType.MODEL, Category.CategoryType.FILE]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no changes written."))

        for ctype in types:
            for i, node in enumerate(CATEGORY_TREE, start=1):
                if dry_run:
                    continue

                root = _upsert_root(ctype=ctype, name=node.name, sort_order=i)

                # children
                for j, child_name in enumerate(node.children, start=1):
                    _upsert_child(ctype=ctype, parent=root, name=child_name, sort_order=j)

        after_total = Category.objects.count()

        # Rough reporting:
        # - If wipe was used, everything is "created".
        # - Otherwise, after_total - before_total is new rows created.
        if dry_run:
            # estimate would require simulating existence checks; keep it simple
            self.stdout.write(self.style.SUCCESS("Done. (dry-run)"))
            return

        if wipe:
            created_count = after_total
        else:
            created_count = max(0, after_total - before_total)

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete. wipe={wipe} created~={created_count} total={after_total}"
        ))
