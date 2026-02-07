from __future__ import annotations

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category


MODEL_TREE = [
    ("Art & Sculptures", ["Busts & Statues", "Abstract", "Animals", "Mythical Creatures", "Mini Sculptures", "Wall Art (3D)"]),
    ("Home & Decor", ["Vases & Planters", "Lamps & Shades", "Wall Hooks & Hangers", "Signs & Nameplates", "Picture Frames", "Coasters & Trays", "Bathroom Accessories"]),
    ("Household & Organization", ["Drawer Organizers", "Cable Management", "Kitchen Organizers", "Pantry & Spice Racks", "Storage Boxes", "Closet & Hangers", "Cleaning & Utility"]),
    ("Tools & Workshop", ["Tool Holders", "Drill / Bit Organizers", "Jigs & Guides", "Clamps & Mounts", "Bench Accessories", "Hardware Bins", "Measuring / Layout"]),
    ("Automotive", ["Interior Accessories", "Phone Mounts", "Console Organizers", "Cup Holders", "Dash Clips", "Key / FOB Holders"]),
    ("Electronics & Tech", ["Phone Stands", "Tablet Stands", "Headphone Stands", "Controller Stands", "Desk Accessories", "Raspberry Pi / SBC Cases", "Cable Clips"]),
    ("Gaming & Toys", ["Board Game Accessories", "Dice Towers & Trays", "Card Holders", "Puzzle Toys", "Educational Toys", "Fidget Toys"]),
    ("Miniatures & Terrain", ["Terrain Pieces", "Buildings & Scenery", "Scatter Terrain", "Bases & Base Toppers", "Storage & Transport"]),
    ("Cosplay & Props", ["Wearable Props", "Helmets & Masks", "Armor Parts", "Prop Weapons (Non-functional)", "Costume Accessories", "Display Stands"]),
    ("Jewelry & Accessories", ["Earrings", "Pendants", "Rings", "Keychains", "Hair Accessories", "Display & Holders"]),
    ("Pets", ["Food Scoops", "Leash Hooks", "Toy Storage", "Pet Tag Holders", "Small Pet Accessories"]),
    ("Seasonal & Holiday", ["Ornaments", "Decorations", "Gift Tags / Toppers", "Halloween", "Christmas", "Easter", "Valentine’s"]),
]

FILE_TREE = [
    ("Functional Parts", ["Brackets & Mounts", "Hooks & Hangers", "Replacement Parts", "Clips & Fasteners", "Enclosures / Cases", "Workshop Jigs"]),
    ("Household & Organization (Files)", ["Drawer Organizers", "Kitchen Organization", "Bathroom Accessories", "Storage Boxes", "Labels / Tags", "Cable Management"]),
    ("Home & Decor (Files)", ["Vases & Planters", "Lamps & Shades", "Wall Art", "Signs & Nameplates", "Decorative Sculptures", "Planter Accessories"]),
    ("Toys & Games (Files)", ["Fidget Toys", "Puzzle Toys", "Board Game Accessories", "Dice Towers & Trays", "Card Accessories", "Educational"]),
    ("Miniatures & Terrain (Files)", ["Terrain", "Buildings", "Scatter", "Bases", "Modular Systems", "RPG / Wargaming"]),
    ("Cosplay & Props (Files)", ["Helmets & Masks", "Armor", "Accessories", "Prop Parts", "Display Stands", "Pattern / Sizing Tools"]),
    ("Figures & Characters (Files)", ["Fantasy", "Sci-Fi", "Creatures", "Robots / Mechs", "Busts"]),
    ("Automotive (Files)", ["Interior Accessories", "Mounts & Brackets", "Console Inserts", "Clips & Fasteners", "Custom Emblems (generic)"]),
    ("Electronics & Tech (Files)", ["Phone / Tablet Stands", "Controller Stands", "Headphone Stands", "Raspberry Pi / SBC Cases", "Cable Management", "Adapter Plates"]),
    ("Jewelry & Accessories (Files)", ["Earrings", "Pendants", "Rings", "Keychains", "Display Stands"]),
    ("RC / Hobby (Files)", ["RC Parts", "Drone Accessories", "Model Accessories", "Scale Details", "Mounts & Clips"]),
    ("Bundles", ["Value Packs", "Themed Collections", "Starter Packs", "Terrain Bundles", "Organizer Bundles"]),
]


def _upsert(*, type_: str, name: str, parent: Category | None, sort_order: int) -> tuple[Category, bool]:
    obj = Category.objects.filter(type=type_, parent=parent, name=name).first()
    created = False
    if not obj:
        obj = Category(type=type_, parent=parent, name=name, slug="")
        created = True

    obj.is_active = True
    obj.sort_order = int(sort_order)
    obj.save()
    return obj, created


class Command(BaseCommand):
    help = "Seed MODEL + FILE categories/subcategories (idempotent) and clear sidebar cache."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate active categories not present in this seed set.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        deactivate_missing = bool(options["deactivate_missing"])

        created = 0
        updated = 0
        seed_keys: set[tuple[str, int | None, str]] = set()

        def process(type_: str, tree: list[tuple[str, list[str]]]):
            nonlocal created, updated
            root_sort = 0
            for root_name, children in tree:
                root_sort += 10
                if dry_run:
                    self.stdout.write(f"[DRY] ROOT {type_}: {root_name}")
                    root_obj = None
                else:
                    root_obj, was_created = _upsert(type_=type_, name=root_name, parent=None, sort_order=root_sort)
                    seed_keys.add((type_, None, root_name))
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

                child_sort = 0
                for child_name in children:
                    child_sort += 10
                    if dry_run:
                        self.stdout.write(f"   [DRY] - {child_name}")
                        continue
                    assert root_obj is not None
                    _, was_created = _upsert(type_=type_, name=child_name, parent=root_obj, sort_order=child_sort)
                    seed_keys.add((type_, root_obj.id, child_name))
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

        process(Category.CategoryType.MODEL, MODEL_TREE)
        process(Category.CategoryType.FILE, FILE_TREE)

        if (not dry_run) and deactivate_missing:
            deactivated = 0
            for c in Category.objects.filter(is_active=True).iterator():
                key = (c.type, c.parent_id, c.name)
                if key not in seed_keys:
                    c.is_active = False
                    c.save(update_fields=["is_active", "updated_at"])
                    deactivated += 1
            self.stdout.write(self.style.WARNING(f"Deactivated {deactivated} categories not in seed set."))

        if not dry_run:
            cache.delete("sidebar_categories_v2")
            self.stdout.write(self.style.SUCCESS("Cleared cache key sidebar_categories_v2."))

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} updated={updated} dry_run={dry_run}"))
