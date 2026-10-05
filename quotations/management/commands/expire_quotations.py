from django.core.management.base import BaseCommand
from django.utils import timezone

from quotations.models import Quotation


class Command(BaseCommand):
    help = "Mark Draft and Sent quotations past their Valid Until date as Expired."

    def handle(self, *args, **options):
        today = timezone.localdate()
        count = Quotation.objects.filter(
            status__in=[Quotation.DRAFT, Quotation.SENT],
            valid_until__lt=today,
        ).update(status=Quotation.EXPIRED, updated_at=timezone.now())
        self.stdout.write(
            self.style.SUCCESS(f"{count} quotation(s) marked as expired.")
        )
