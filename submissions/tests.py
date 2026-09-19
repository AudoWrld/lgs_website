from django.test import TestCase
from django.urls import reverse
from django.utils.text import slugify

from accounts.models import Client, User
from submissions.models import Submission


class SubmissionSlugTests(TestCase):
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

    def test_submission_slug_is_generated_from_reference(self):
        self.assertTrue(self.submission.slug)
        self.assertEqual(self.submission.slug, slugify(self.submission.reference))

    def test_sample_registration_detail_url_uses_slug(self):
        url = reverse("reception:sample_registration_detail", args=[self.submission.slug])
        self.assertIn(self.submission.slug, url)
