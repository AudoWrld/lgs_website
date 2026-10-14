from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from quotations.models import Quotation


class Command(BaseCommand):
    help = (
        "Expire quotations that are past their Valid Until date by setting expired_at."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report count only, change nothing",
        )
        parser.add_argument(
            "--as-of",
            type=str,
            help="Treat that date as today, for testing (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        if options["as_of"]:
            try:
                today = datetime.strptime(options["as_of"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("Invalid date format. Use YYYY-MM-DD.")
        else:
            today = timezone.localdate()

        queryset = Quotation.objects.filter(
            expired_at__isnull=True, valid_until__lt=today
        )

        if options["dry_run"]:
            count = queryset.count()
            self.stdout.write(f"[dry-run] {count} quotation(s) would be expired.")
            return

        with transaction.atomic():
            updated = queryset.update(expired_at=timezone.now())

        self.stdout.write(self.style.SUCCESS(f"Expired {updated} quotation(s)."))
