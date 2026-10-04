from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Client, User
from chemist.models import MetallurgicalTestEntry, MineralAnalysisEntry
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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class MissingWorksheetTests(TestCase):
    def setUp(self):
        self.chemist = User.objects.create_chemist(email="worksheet-chemist@example.com")
        client_record = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Worksheet Test Client",
            contact_person="Jane Client",
            email="worksheet-client@example.com",
            whatsapp_number="123456789",
        )
        self.submission = Submission.objects.create(
            client=client_record,
            is_submitted=True,
            status=Submission.SUBMITTED_TO_LAB,
        )
        self.sample = Sample.objects.create(
            submission=self.submission,
            client_sample_id="SAMPLE-01",
            sample_type=Sample.ROCK,
            analysis_status=Sample.SUBMITTED_TO_LAB,
        )
        self.service = Service.objects.create(
            name="Gold & Copper Analysis",
            method_of_analysis="Aqua Regia + AAS",
            pricing_type=Service.FIXED,
            unit_price=10,
        )
        SampleService.objects.create(sample=self.sample, service=self.service)
        self.client.force_login(self.chemist)

    def test_mineral_search_reports_missing_worksheet(self):
        response = self.client.get(
            reverse(
                "chemist:mineral_analysis_samples",
                args=[self.submission.reference],
            )
        )

        self.assertContains(response, "worksheet has not been generated")
        self.assertNotContains(response, "chemist/mineral-analysis/entry/")

    def test_mineral_entry_does_not_create_without_worksheet(self):
        response = self.client.get(
            reverse("chemist:mineral_analysis_entry", args=[self.sample.slug])
        )

        self.assertRedirects(response, reverse("chemist:chemist_dashboard"))
        self.assertFalse(MineralAnalysisEntry.objects.filter(sample=self.sample).exists())

    def test_metallurgical_search_reports_missing_worksheet(self):
        sample = Sample.objects.create(
            submission=self.submission,
            client_sample_id="CYANIDE-01",
            sample_type=Sample.ROCK,
            analysis_status=Sample.SUBMITTED_TO_LAB,
        )
        service = Service.objects.create(
            name="Conventional Cyanide Test",
            method_of_analysis="Bottle Test + AAS",
            pricing_type=Service.FIXED,
            unit_price=10,
            metallurgical_type=Service.CYANIDE_CONVENTIONAL,
        )
        SampleService.objects.create(sample=sample, service=service)

        response = self.client.get(
            reverse(
                "chemist:metallurgical_tests_samples",
                args=[self.submission.reference],
            )
        )

        self.assertContains(response, "required worksheet has not been generated")
        self.assertNotContains(response, "chemist/metallurgical-tests/entry/")

    def test_metallurgical_entry_does_not_create_without_worksheet(self):
        sample = Sample.objects.create(
            submission=self.submission,
            client_sample_id="CYANIDE-02",
            sample_type=Sample.ROCK,
            analysis_status=Sample.SUBMITTED_TO_LAB,
        )
        service = Service.objects.create(
            name="Optimization Cyanide Test",
            method_of_analysis="Bottle Test + AAS",
            pricing_type=Service.FIXED,
            unit_price=10,
            metallurgical_type=Service.CYANIDE_OPTIMIZATION,
        )
        SampleService.objects.create(sample=sample, service=service)

        response = self.client.get(
            reverse("chemist:metallurgical_tests_entry", args=[sample.slug])
        )

        self.assertRedirects(response, reverse("chemist:chemist_dashboard"))
        self.assertFalse(MetallurgicalTestEntry.objects.filter(sample=sample).exists())


