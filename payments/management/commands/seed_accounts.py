from django.core.management.base import BaseCommand
from django.db import transaction

from payments.models import PaymentAccount

ACCOUNT_NAME = "Bahati Lunyilija Charles"

ACCOUNTS = [
    {
        "account_type": PaymentAccount.MOBILE,
        "bank_name": "M-Pesa Vodacom",
        "account_name": ACCOUNT_NAME,
        "account_number": "0797 717 883",
        "display_order": 1,
    },
    {
        "account_type": PaymentAccount.BANK,
        "bank_name": "NMB Bank",
        "account_name": ACCOUNT_NAME,
        "account_number": "33510029733",
        "display_order": 2,
    },
    {
        "account_type": PaymentAccount.BANK,
        "bank_name": "NBC Bank",
        "account_name": ACCOUNT_NAME,
        "account_number": "016171068961",
        "display_order": 3,
    },
    {
        "account_type": PaymentAccount.MOBILE,
        "bank_name": "Selcom",
        "account_name": ACCOUNT_NAME,
        "account_number": "0753 192 863",
        "display_order": 4,
    },
]


class Command(BaseCommand):
    help = "Create or update the official LGS payment accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        for data in ACCOUNTS:
            lookup = {
                "account_type": data["account_type"],
                "account_number": data["account_number"],
            }
            defaults = {
                "bank_name": data["bank_name"],
                "account_name": data["account_name"],
                "display_order": data["display_order"],
                "is_active": True,
            }
            account, created = PaymentAccount.objects.update_or_create(
                defaults=defaults, **lookup
            )
            account.full_clean()
            label = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{label}: {data['bank_name']} — {data['account_number']}"
                )
            )
