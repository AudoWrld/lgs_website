from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.utils import generate_temp_password

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Generate and save a plaintext temporary password for every client "
        "account that has not yet set their own password (must_change_password=True)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing initial_temp_password values instead of skipping them.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        qs = User.objects.filter(role=User.CUSTOMER, must_change_password=True)

        if not force:
            qs = qs.filter(initial_temp_password__isnull=True)

        updated = 0
        for user in qs:
            password = generate_temp_password()
            user.set_password(password)
            user.initial_temp_password = password
            user.save(update_fields=["password", "initial_temp_password"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Set temporary passwords for {updated} client account(s)."
            )
        )