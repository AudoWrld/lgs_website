from decimal import Decimal
from django.core.management.base import BaseCommand
from samples.models import Service

SERVICES = [
    {
        "name": "Gold & Copper Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30000.00"),
        "metallurgical_type": Service.NONE,
    },
    {
        "name": "Gold, Copper & Silver Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("40000.00"),
        "metallurgical_type": Service.NONE,
    },
    {
        "name": "Gold, Copper & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("40000.00"),
        "metallurgical_type": Service.NONE,
    },
    {
        "name": "Gold, Copper, Silver & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("50000.00"),
        "metallurgical_type": Service.NONE,
    },
    {
        "name": "Multi-Element Analysis",
        "method_of_analysis": "X-Ray Fluorescence",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("50000.00"),
        "metallurgical_type": Service.NONE,
    },
    {
        "name": "Conventional Cyanide Leaching Test",
        "method_of_analysis": "Cyanide Leaching Test Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30000.00"),
        "metallurgical_type": Service.CYANIDE_CONVENTIONAL,
    },
    {
        "name": "Cyanide Leaching Parameter Optimization",
        "method_of_analysis": "Cyanide Leaching Parameter Optimization Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
        "metallurgical_type": Service.CYANIDE_OPTIMIZATION,
    },
    {
        "name": "Carbon Activity Test",
        "method_of_analysis": "Carbon Activity Test Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30000.00"),
        "metallurgical_type": Service.CARBON_ACTIVITY,
    },
    {
        "name": "Metallic Screening and Gold Evaluation",
        "method_of_analysis": "Metallic Screening Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
        "metallurgical_type": Service.NONE,
    },
]

STALE_SERVICE_NAMES = ["Mineral Analysis", "Metallurgical Testing"]


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
            service = Service(
                name=entry["name"],
                method_of_analysis=entry["method_of_analysis"],
                pricing_type=entry["pricing_type"],
                unit_price=entry["unit_price"],
                metallurgical_type=entry["metallurgical_type"],
                is_active=True,
            )
            service.full_clean(exclude=["id"], validate_unique=False)

            service, created = Service.objects.update_or_create(
                name=entry["name"],
                defaults={
                    "method_of_analysis": entry["method_of_analysis"],
                    "pricing_type": entry["pricing_type"],
                    "unit_price": entry["unit_price"],
                    "metallurgical_type": entry["metallurgical_type"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        for stale_name in STALE_SERVICE_NAMES:
            stale = Service.objects.filter(name=stale_name).first()
            if stale is None:
                continue
            if stale.sample_services.exists():
                stale.is_active = False
                stale.save(update_fields=["is_active"])
                self.stdout.write(
                    self.style.WARNING(
                        f"Deactivated (still referenced by existing samples): {stale.name}"
                    )
                )
            else:
                stale.delete()
                self.stdout.write(
                    self.style.WARNING(f"Deleted unused placeholder: {stale.name}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {created_count} created, {updated_count} updated, "
                f"{Service.objects.count()} total active services."
            )
        )
