from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category


# One master tree. We seed it twice: once for MODEL and once for FILE.
CATEGORY_TREE: list[dict[str, Any]] = [
    {
        "name": "Art & Sculptures",
        "children": [
            "Abstract",
            "Busts & Statues",
            "Wall Art",
            "Vases",
            "Figurative",
            "Anime & Fan Art",
            "Fantasy",
            "Sci-Fi",
        ],
    },
    {
        "name": "Miniatures & Terrain",
        "children": [
            "Tabletop Minis",
            "Terrain Tiles",
            "Buildings",
            "Scatter Props",
            "Bases",
            "Dungeon",
            "Sci-Fi Terrain",
            "Fantasy Terrain",
        ],
    },
    {
        "name": "Figurines",
        "children": [
            "Animals",
            "Characters",
            "Chibi",
            "Robots",
            "Monsters",
            "Superheroes",
            "Video Game",
            "Collectibles",
        ],
    },
    {
        "name": "Cosplay & Props",
        "children": [
            "Armor Parts",
            "Helmets & Masks",
            "Weapons (Props)",
            "Accessories",
            "Emblems & Badges",
            "Costume Hardware",
            "Display Stands",
        ],
    },
    {
        "name": "Toys & Games",
        "children": [
            "Board Game Inserts",
            "Dice & Accessories",
            "Puzzles",
            "Educational Toys",
            "Building Blocks",
            "Fidget Toys",
            "Game Tokens",
        ],
    },
    {
        "name": "Household & Organization",
        "children": [
            "Hooks & Hangers",
            "Storage Bins",
            "Drawer Organizers",
            "Cable Management",
            "Bathroom",
            "Laundry",
            "Garage",
            "Wall Mounts",
        ],
    },
    {
        "name": "Home & Decor",
        "children": [
            "Planters",
            "Candles & Holders",
            "Frames",
            "Clocks",
            "Seasonal Decor",
            "Signs & Plaques",
            "Lighting Shades",
        ],
    },
    {
        "name": "Kitchen & Dining",
        "children": [
            "Utensils",
            "Containers",
            "Coffee & Tea",
            "Spice Racks",
            "Cookie Cutters",
            "Bottle Openers",
            "Stands & Holders",
        ],
    },
    {
        "name": "Office & Desk",
        "children": [
            "Phone Stands",
            "Tablet Stands",
            "Pen Holders",
            "Desk Organizers",
            "Headphone Stands",
            "Monitor Accessories",
            "Laptop Risers",
        ],
    },
    {
        "name": "Electronics & Tech",
        "children": [
            "Cases",
            "Mounts",
            "Adapters",
            "Raspberry Pi",
            "Arduino",
            "Cable Clips",
            "Camera Mounts",
            "Battery Holders",
        ],
    },
    {
        "name": "Tools & Workshop",
        "children": [
            "Tool Holders",
            "Jigs",
            "Templates",
            "Pegboard",
            "Measuring Aids",
            "Bit Holders",
            "Workbench Accessories",
        ],
    },
    {
        "name": "Automotive",
        "children": [
            "Interior Accessories",
            "Phone Mounts",
            "Clips & Fasteners",
            "Organizers",
            "Detailing Tools",
            "Gauges & Pods",
        ],
    },
    {
        "name": "Outdoors & Garden",
        "children": [
            "Garden Tools",
            "Irrigation",
            "Camping",
            "Hiking",
            "Birdhouses & Feeders",
            "Outdoor Mounts",
        ],
    },
    {
        "name": "Pets & Animals",
        "children": [
            "Pet Toys",
            "Feeding Accessories",
            "Aquarium",
            "Leash & Collar",
            "Grooming",
            "Pet Organization",
        ],
    },
    {
        "name": "Jewelry & Accessories",
        "children": [
            "Rings",
            "Pendants",
            "Earrings",
            "Bracelets",
            "Jewelry Boxes",
            "Display Stands",
        ],
    },
    {
        "name": "Fashion & Wearables",
        "children": [
            "Belt Clips",
            "Buttons",
            "Buckles",
            "Shoe Accessories",
            "Wearable Tech Mounts",
        ],
    },
    {
        "name": "Sports & Fitness",
        "children": [
            "Bottle Holders",
            "Gym Accessories",
            "Bike Accessories",
            "Skate Accessories",
            "Sports Gear Mounts",
        ],
    },
    {
        "name": "Photography & Video",
        "children": [
            "Tripod Accessories",
            "GoPro",
            "Light Mounts",
            "Camera Rigs",
            "Cable/Accessory Holders",
        ],
    },
    {
        "name": "Music & Audio",
        "children": [
            "Instrument Accessories",
            "Mic Mounts",
            "Headphone Accessories",
            "Cable Management (Audio)",
        ],
    },
    {
        "name": "Science & Education",
        "children": [
            "STEM Models",
            "Molecules",
            "Anatomy",
            "Math Aids",
            "Physics Demonstrations",
        ],
    },
    {
        "name": "Robotics & Drones",
        "children": [
            "Frames",
            "Mounts",
            "Arms & Brackets",
            "Battery Trays",
            "Sensor Mounts",
        ],
    },
    {
        "name": "RC & Model Kits",
        "children": [
            "Airplanes",
            "Cars",
            "Boats",
            "Upgrades",
            "Parts & Spares",
        ],
    },
    {
        "name": "Architecture & Models",
        "children": [
            "Buildings",
            "Furniture Miniatures",
            "City Models",
            "Scale Accessories",
        ],
    },
    {
        "name": "Holiday & Seasonal",
        "children": [
            "Christmas",
            "Halloween",
            "Easter",
            "Valentine’s",
            "Thanksgiving",
            "New Year",
        ],
    },
    {
        "name": "Replacement Parts",
        "children": [
            "Appliance Parts",
            "Furniture Parts",
            "Electronics Parts",
            "Automotive Clips",
            "Knobs & Handles",
        ],
    },
    {
        "name": "Functional Parts",
        "children": [
            "Brackets",
            "Clamps",
            "Gears",
            "Enclosures",
            "Connectors",
            "Spacers & Shims",
        ],
    },
]


@dataclass(frozen=True)
class SeedStats:
    created: int = 0
    updated: int = 0


def _slug(name: str) -> str:
    return (slugify(name) or "").strip()[:140] or "category"


def _upsert_category(*, type_value: str, name: str, parent: Category | None, sort_order: int) -> tuple[Category, bool]:
    """
    Upsert by unique_together (type, parent, slug).
    Name/description/is_active/sort_order are enforced on every run.
    """
    slug = _slug(name)
    obj, created = Category.objects.update_or_create(
        type=type_value,
        parent=parent,
        slug=slug,
        defaults={
            "name": name.strip(),
            "is_active": True,
            "sort_order": int(sort_order),
        },
    )
    return obj, created


class Command(BaseCommand):
    help = "Seed a robust set of categories + subcategories for both MODEL and FILE types."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete all categories before seeding (DANGEROUS).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        wipe = bool(options.get("wipe"))

        if wipe:
            self.stdout.write(self.style.WARNING("WIPING ALL Category rows..."))
            Category.objects.all().delete()

        created = 0
        updated = 0

        # Seed for both types using the same tree
        for type_value in (Category.CategoryType.MODEL, Category.CategoryType.FILE):
            type_prefix = "MODEL" if type_value == Category.CategoryType.MODEL else "FILE"

            for i, node in enumerate(CATEGORY_TREE, start=1):
                root_name = str(node["name"]).strip()
                children = list(node.get("children") or [])

                root_obj, root_created = _upsert_category(
                    type_value=type_value,
                    name=root_name,
                    parent=None,
                    sort_order=i,
                )
                if root_created:
                    created += 1
                else:
                    updated += 1

                # children
                for j, child_name in enumerate(children, start=1):
                    child_obj, child_created = _upsert_category(
                        type_value=type_value,
                        name=str(child_name).strip(),
                        parent=root_obj,
                        sort_order=j,
                    )
                    if child_created:
                        created += 1
                    else:
                        updated += 1

            self.stdout.write(self.style.SUCCESS(f"{type_prefix}: seeded OK"))

        total = Category.objects.count()
        roots = Category.objects.filter(parent__isnull=True).count()
        subs = total - roots

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete. wipe={wipe} created={created} updated={updated} total={total} roots={roots} subs={subs}"
            )
        )
