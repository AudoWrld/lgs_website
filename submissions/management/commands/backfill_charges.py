from django.core.management.base import BaseCommand
from django.db import transaction

from samples.models import Service
from submissions.models import Submission


class Command(BaseCommand):
    help = (
        "Freeze service charges for submissions that were submitted before "
        "charges were stored, and refresh their payment gross amounts."
    )

    def handle(self, *args, **options):
        pending = Submission.objects.filter(
            is_submitted=True,
            samples__sample_services__charged_price__isnull=True,
            samples__sample_services__service__pricing_type=Service.FIXED,
        ).distinct()

        processed = 0
        for submission in pending:
            with transaction.atomic():
                submission.snapshot_charges()
                submission.refresh_payment_gross()
            processed += 1
            self.stdout.write(f"{submission.reference} updated.")

        self.stdout.write(
            self.style.SUCCESS(f"Backfill complete: {processed} submission(s) updated.")
        )
