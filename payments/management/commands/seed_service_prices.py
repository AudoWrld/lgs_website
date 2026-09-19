from decimal import Decimal

from django.core.management.base import BaseCommand

from samples.models import Service

PRICING = [
    (
        "Gold & Copper Analysis",
        "Aqua Regia Digestion + AAS",
        Service.FIXED,
        Decimal("30000.00"),
    ),
    (
        "Gold, Copper & Silver Analysis",
        "Aqua Regia Digestion + AAS",
        Service.FIXED,
        Decimal("40000.00"),
    ),
    (
        "Gold, Copper & Sulphur Analysis",
        "Aqua Regia Digestion + AAS / Furnace Induction",
        Service.FIXED,
        Decimal("40000.00"),
    ),
    (
        "Gold, Copper, Silver & Sulphur Analysis",
        "Aqua Regia Digestion + AAS / Furnace Induction",
        Service.FIXED,
        Decimal("50000.00"),
    ),
    (
        "Conventional Cyanide Leaching Test",
        "Bottle Test + AAS",
        Service.FIXED,
        Decimal("30000.00"),
    ),
    (
        "Carbon Activity Test",
        "Carbon Activity Test Method",
        Service.FIXED,
        Decimal("30000.00"),
    ),
    (
        "Multi-Element Analysis",
        "X-Ray Fluorescence (XRF)",
        Service.FIXED,
        Decimal("50000.00"),
    ),
    (
        "Metallic Screening and Gold Evaluation",
        "Aqua Regia + AAS / Bottle Roll Method",
        Service.QUOTATION,
        None,
    ),
    (
        "Cyanide Leaching Parameter Optimization",
        "Bottle Test + AAS",
        Service.QUOTATION,
        None,
    ),
]

STALE_SERVICE_NAMES = ["Metallurgical Testing", "Mineral Analysis"]


class Command(BaseCommand):
    help = "Seeds or corrects Service records to match the official LGS pricing table, and removes non-billable category placeholders."

    def handle(self, *args, **options):
        for name, method, pricing_type, price in PRICING:
            service, created = Service.objects.update_or_create(
                name=name,
                defaults={
                    "method_of_analysis": method,
                    "pricing_type": pricing_type,
                    "unit_price": price,
                    "is_active": True,
                },
            )
            action = "Created" if created else "Updated"
            price_display = f"TZS {price:,.2f}" if price is not None else "By Quotation"
            self.stdout.write(
                self.style.SUCCESS(f"{action}: {service.name} — {price_display}")
            )

        for stale_name in STALE_SERVICE_NAMES:
            stale = Service.objects.filter(name=stale_name).first()
            if stale:
                in_use = stale.sample_services.exists()
                if in_use:
                    stale.is_active = False
                    stale.save(update_fields=["is_active"])
                    self.stdout.write(
                        self.style.WARNING(
                            f"Deactivated (still referenced by existing samples, not deleted): {stale.name}"
                        )
                    )
                else:
                    stale.delete()
                    self.stdout.write(
                        self.style.WARNING(f"Deleted unused placeholder: {stale.name}")
                    )
