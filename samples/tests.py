from django.test import TestCase
from django.urls import reverse

from accounts.models import Client, User
from samples.models import Sample, Service
from submissions.models import Submission


class SampleSlugTests(TestCase):
    def setUp(self):
        self.reception = User.objects.create_reception(
            email="reception@example.com",
            password="TestPass123!",
        )
        self.client = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Acme Labs",
            contact_person="Jane Doe",
            email="acme@example.com",
            whatsapp_number="123456789",
            registered_by=self.reception,
        )
        self.submission = Submission.objects.create(
            client=self.client,
            registered_by=self.reception,
        )
        self.service = Service.objects.create(
            name="Assay A",
            method_of_analysis="ICP-OES",
            pricing_type=Service.FIXED,
            unit_price=10,
        )

    def test_sample_slug_is_generated_from_submission_reference(self):
        sample = Sample.objects.create(
            submission=self.submission,
            client_sample_id="A-001",
            sample_type=Sample.ROCK,
        )
        sample.services.add(self.service)
        self.assertTrue(sample.slug)
        self.assertIn(self.submission.slug, sample.slug)
        self.assertEqual(sample.slug, f"{self.submission.slug}-01")

    def test_sample_edit_url_uses_slug(self):
        sample = Sample.objects.create(
            submission=self.submission,
            client_sample_id="A-001",
            sample_type=Sample.ROCK,
        )
        sample.services.add(self.service)
        url = reverse(
            "reception:sample_edit",
            args=[self.submission.slug, sample.slug],
        )
        self.assertIn(sample.slug, url)
