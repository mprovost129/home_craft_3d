from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category


@dataclass(frozen=True)
class SeedNode:
    name: str
    children: Sequence["SeedNode"] = ()


def ensure_category(*, type_value: str, name: str, parent: Category | None) -> Category:
    """
    Idempotent upsert for your schema:
      unique_together = (type, parent, slug)
    """
    slug = slugify(name)[:140]

    obj, _created = Category.objects.get_or_create(
        type=type_value,
        parent=parent,
        slug=slug,
        defaults={
            "name": name,
            "is_active": True,
            "sort_order": 0,
        },
    )

    # Keep name/active synced (safe if renamed)
    obj.name = name
    obj.is_active = True
    if not obj.slug:
        obj.slug = slug
    obj.save()
    return obj


def seed_tree(*, type_value: str, nodes: Sequence[SeedNode], parent: Category | None = None) -> None:
    for node in nodes:
        cat = ensure_category(type_value=type_value, name=node.name, parent=parent)
        if node.children:
            seed_tree(type_value=type_value, nodes=node.children, parent=cat)


def get_seed_data():
    model_tree = [
        SeedNode("Miniatures", children=(
            SeedNode("Fantasy"),
            SeedNode("Sci-Fi"),
            SeedNode("Animals"),
            SeedNode("Military"),
            SeedNode("Vehicles"),
        )),
        SeedNode("Figurines", children=(
            SeedNode("Characters"),
            SeedNode("Busts"),
            SeedNode("Chibi"),
        )),
        SeedNode("Props & Cosplay", children=(
            SeedNode("Helmets"),
            SeedNode("Weapons"),
            SeedNode("Armor Parts"),
            SeedNode("Accessories"),
        )),
        SeedNode("Home & Decor", children=(
            SeedNode("Vases"),
            SeedNode("Wall Art"),
            SeedNode("Planters"),
            SeedNode("Lighting"),
        )),
        SeedNode("Tools & Fixtures", children=(
            SeedNode("Jigs"),
            SeedNode("Clamps"),
            SeedNode("Workshop"),
            SeedNode("Mounts & Brackets"),
        )),
        SeedNode("Games & Toys", children=(
            SeedNode("Board Games"),
            SeedNode("Tabletop"),
            SeedNode("Puzzle Toys"),
            SeedNode("Kids"),
        )),
        SeedNode("Automotive", children=(
            SeedNode("Interior"),
            SeedNode("Exterior"),
            SeedNode("Holders & Clips"),
        )),
        SeedNode("Organizers", children=(
            SeedNode("Desk"),
            SeedNode("Kitchen"),
            SeedNode("Garage"),
            SeedNode("Cable Management"),
        )),
        SeedNode("Educational", children=(
            SeedNode("STEM"),
            SeedNode("Models"),
            SeedNode("Architecture"),
        )),
        SeedNode("Terrain & Diorama", children=(
            SeedNode("Buildings"),
            SeedNode("Scatter"),
            SeedNode("Bases"),
        )),
    ]

    file_tree = [
        SeedNode("Bundles", children=(
            SeedNode("Collections"),
            SeedNode("Mega Packs"),
        )),
        SeedNode("Miniatures (Files)", children=(
            SeedNode("Fantasy"),
            SeedNode("Sci-Fi"),
            SeedNode("Animals"),
        )),
        SeedNode("Cosplay (Files)", children=(
            SeedNode("Helmets"),
            SeedNode("Armor"),
            SeedNode("Props"),
        )),
        SeedNode("Functional Parts (Files)", children=(
            SeedNode("Replacement Parts"),
            SeedNode("Adapters"),
            SeedNode("Mounts & Brackets"),
        )),
        SeedNode("Household (Files)", children=(
            SeedNode("Kitchen"),
            SeedNode("Bathroom"),
            SeedNode("Laundry"),
        )),
        SeedNode("Organizers (Files)", children=(
            SeedNode("Desk"),
            SeedNode("Toolbox"),
            SeedNode("Cable Management"),
        )),
        SeedNode("Terrain (Files)", children=(
            SeedNode("Buildings"),
            SeedNode("Scatter"),
            SeedNode("Bases"),
        )),
        SeedNode("Art & Sculptures (Files)", children=(
            SeedNode("Abstract"),
            SeedNode("Statues"),
            SeedNode("Wall / Relief"),
        )),
        SeedNode("Seasonal (Files)", children=(
            SeedNode("Halloween"),
            SeedNode("Christmas"),
            SeedNode("Easter"),
        )),
    ]

    return model_tree, file_tree


class Command(BaseCommand):
    help = "Seed default MODEL and FILE categories/subcategories (idempotent). Use --clear to wipe first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all categories before seeding (ONLY if no products are linked yet).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get("clear"):
            self.stdout.write(self.style.WARNING("Clearing ALL categories..."))
            Category.objects.all().delete()

        model_tree, file_tree = get_seed_data()

        self.stdout.write("Seeding 3D Models category tree...")
        seed_tree(type_value=Category.CategoryType.MODEL, nodes=model_tree)

        self.stdout.write("Seeding 3D Files category tree...")
        seed_tree(type_value=Category.CategoryType.FILE, nodes=file_tree)

        self.stdout.write(self.style.SUCCESS("Done seeding categories."))
