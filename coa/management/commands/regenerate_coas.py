import time

from django.core.management.base import BaseCommand, CommandError

from coa.models import COA
from coa.services import attach_files


class Command(BaseCommand):
    help = "Rebuild the PDF and PNG files of already generated COAs."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="all_coas")
        parser.add_argument("--ref", action="append", default=[], dest="refs")
        parser.add_argument("--status", action="append", default=[], dest="statuses")
        parser.add_argument("--base-url", default=None, dest="base_url")

    def handle(self, *args, **options):
        refs = options["refs"]
        statuses = options["statuses"]
        if not (options["all_coas"] or refs or statuses):
            raise CommandError("Use --all, --ref COA_NUMBER or --status STATUS.")

        queryset = COA.objects.select_related(
            "submission", "submission__client", "group"
        ).order_by("id")
        if refs:
            queryset = queryset.filter(coa_number__in=refs)
        if statuses:
            queryset = queryset.filter(status__in=statuses)

        done = 0
        failed = 0
        started = time.time()
        for coa in queryset:
            try:
                if coa.pdf_file:
                    coa.pdf_file.delete(save=False)
                if coa.png_file:
                    coa.png_file.delete(save=False)
                attach_files(coa, base_url=options["base_url"])
                done += 1
                self.stdout.write(f"OK      {coa.coa_number}")
            except Exception as exc:
                failed += 1
                self.stderr.write(f"FAILED  {coa.coa_number}: {exc}")

        elapsed = time.time() - started
        self.stdout.write(f"Regenerated {done}, failed {failed}, {elapsed:.1f}s")
