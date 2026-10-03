from decimal import Decimal

from django.test import TestCase

from accounts.models import Client, User
from chemist.models import MineralAnalysisEntry
from samples.models import Sample, SampleService, Service
from submissions.models import Submission


class ReassaySubmissionStatusTests(TestCase):
    def setUp(self):
        self.chemist = User.objects.create_chemist(email="chemist@example.com")
        self.client = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Test Client",
            contact_person="Jane Client",
            email="client@example.com",
            whatsapp_number="123456789",
        )

    def test_submit_to_qc_keeps_reassay_status(self):
        submission = Submission.objects.create(
            client=self.client,
            is_submitted=True,
            status=Submission.SUBMITTED_TO_LAB,
        )
        sample = Sample.objects.create(
            submission=submission,
            client_sample_id="SAMPLE-01",
            sample_type=Sample.ROCK,
            analysis_status=Sample.REASSAY_REQUIRED,
        )
        service = Service.objects.create(
            name="Gold Fire Assay",
            method_of_analysis="Fire assay",
            pricing_type=Service.FIXED,
            unit_price=10,
            tests_gold=True,
        )
        SampleService.objects.create(sample=sample, service=service)

        entry = MineralAnalysisEntry.objects.create(
            sample=sample,
            entered_by=self.chemist,
            status=MineralAnalysisEntry.DRAFT,
            is_reassay=False,
            revision=2,
        )
        entry.ensure_replicates()

        for replicate in entry.replicates.all():
            replicate.weight = Decimal("1.0")
            replicate.au_aas = Decimal("10.0")
            replicate.au_df = Decimal("5.0")
            replicate.save()

        entry.submit_to_qc(self.chemist)

        entry.refresh_from_db()
        sample.refresh_from_db()

        self.assertTrue(entry.is_reassay)
        self.assertEqual(sample.analysis_status, Sample.REASSAY_SUBMITTED)
