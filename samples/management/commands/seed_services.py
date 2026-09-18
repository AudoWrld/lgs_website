from decimal import Decimal
from django.core.management.base import BaseCommand
from samples.models import Service

SERVICES = [
    {
        "name": "Mineral Analysis",
        "method_of_analysis": "Mineralogical Assessment",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
    },
    {
        "name": "Gold & Copper Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("15.00"),
    },
    {
        "name": "Gold, Copper & Silver Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("20.00"),
    },
    {
        "name": "Gold, Copper & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("22.00"),
    },
    {
        "name": "Gold, Copper, Silver & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("28.00"),
    },
    {
        "name": "Multi-Element Analysis",
        "method_of_analysis": "X-Ray Fluorescence",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30.00"),
    },
    {
        "name": "Metallurgical Testing",
        "method_of_analysis": "Metallurgical Test Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
    },
    {
        "name": "Conventional Cyanide Leaching Test",
        "method_of_analysis": "Cyanide Leaching Test Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
    },
    {
        "name": "Cyanide Leaching Parameter Optimization",
        "method_of_analysis": "Cyanide Leaching Parameter Optimization Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
    },
    {
        "name": "Carbon Activity Test",
        "method_of_analysis": "Carbon Activity Test Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("18.00"),
    },
    {
        "name": "Metallic Screening and Gold Evaluation",
        "method_of_analysis": "Metallic Screening Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
    },
]


class Command(BaseCommand):
    help = "Seed the Service table with the services and methods of analysis defined in the LGS Reception Module spec."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing services before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            deleted_count, _ = Service.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted_count} existing services.")
            )

        created_count = 0
        updated_count = 0

        for entry in SERVICES:
            service, created = Service.objects.update_or_create(
                name=entry["name"],
                defaults={
                    "method_of_analysis": entry["method_of_analysis"],
                    "pricing_type": entry["pricing_type"],
                    "unit_price": entry["unit_price"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {created_count} created, {updated_count} updated, "
                f"{Service.objects.count()} total services."
            )
        )
