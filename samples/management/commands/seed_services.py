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
        "tests_gold": True,
        "tests_copper": True,
        "tests_silver": False,
        "tests_sulphur": False,
    },
    {
        "name": "Gold, Copper & Silver Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("40000.00"),
        "metallurgical_type": Service.NONE,
        "tests_gold": True,
        "tests_copper": True,
        "tests_silver": True,
        "tests_sulphur": False,
    },
    {
        "name": "Gold, Copper & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("40000.00"),
        "metallurgical_type": Service.NONE,
        "tests_gold": True,
        "tests_copper": True,
        "tests_silver": False,
        "tests_sulphur": True,
    },
    {
        "name": "Gold, Copper, Silver & Sulphur Analysis",
        "method_of_analysis": "Aqua Regia Digestion + AAS / Sulphur Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("50000.00"),
        "metallurgical_type": Service.NONE,
        "tests_gold": True,
        "tests_copper": True,
        "tests_silver": True,
        "tests_sulphur": True,
    },
    {
        "name": "Multi-Element Analysis",
        "method_of_analysis": "X-Ray Fluorescence",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("50000.00"),
        "metallurgical_type": Service.NONE,
        "tests_gold": False,
        "tests_copper": False,
        "tests_silver": False,
        "tests_sulphur": False,
    },
    {
        "name": "Conventional Cyanide Leaching Test",
        "method_of_analysis": "Cyanide Leaching Test Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30000.00"),
        "metallurgical_type": Service.CYANIDE_CONVENTIONAL,
        "tests_gold": False,
        "tests_copper": False,
        "tests_silver": False,
        "tests_sulphur": False,
    },
    {
        "name": "Cyanide Leaching Parameter Optimization",
        "method_of_analysis": "Cyanide Leaching Parameter Optimization Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
        "metallurgical_type": Service.CYANIDE_OPTIMIZATION,
        "tests_gold": False,
        "tests_copper": False,
        "tests_silver": False,
        "tests_sulphur": False,
    },
    {
        "name": "Carbon Activity Test",
        "method_of_analysis": "Carbon Activity Test Method",
        "pricing_type": Service.FIXED,
        "unit_price": Decimal("30000.00"),
        "metallurgical_type": Service.CARBON_ACTIVITY,
        "tests_gold": False,
        "tests_copper": False,
        "tests_silver": False,
        "tests_sulphur": False,
    },
    {
        "name": "Metallic Screening and Gold Evaluation",
        "method_of_analysis": "Metallic Screening Method",
        "pricing_type": Service.QUOTATION,
        "unit_price": None,
        "metallurgical_type": Service.NONE,
        "tests_gold": True,
        "tests_copper": False,
        "tests_silver": False,
        "tests_sulphur": False,
    },
]

STALE_SERVICE_NAMES = ["Mineral Analysis", "Metallurgical Testing"]

ELEMENT_FLAGS = ("tests_gold", "tests_copper", "tests_silver", "tests_sulphur")


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
            defaults = {
                "method_of_analysis": entry["method_of_analysis"],
                "pricing_type": entry["pricing_type"],
                "unit_price": entry["unit_price"],
                "metallurgical_type": entry["metallurgical_type"],
                "is_active": True,
            }
            for flag in ELEMENT_FLAGS:
                defaults[flag] = entry[flag]

            candidate = Service(name=entry["name"], **defaults)
            candidate.full_clean(exclude=["id"], validate_unique=False)

            service, created = Service.objects.update_or_create(
                name=entry["name"],
                defaults=defaults,
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
                f"{Service.objects.filter(is_active=True).count()} total active services."
            )
        )