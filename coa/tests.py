from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Client
from coa.models import COA
from coa.services import build_coa_doc
from submissions.models import Submission


class COAVerificationTests(TestCase):
	def setUp(self):
		client_record = Client.objects.create(
			client_type=Client.INDIVIDUAL,
			client_name="Verification Client",
			contact_person="Test Contact",
			email="verification@example.com",
			whatsapp_number="123456789",
		)
		self.submission = Submission.objects.create(
			client=client_record,
			is_submitted=True,
		)
		self.coa = COA.objects.create(
			submission=self.submission,
			coa_number=f"{self.submission.reference}-01",
			status=COA.READY_FOR_RELEASE,
		)

	@override_settings(
		STORAGES={
			"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
			"staticfiles": {
				"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
			},
		}
	)
	def test_qr_verification_page_shows_coa_identity_and_status(self):
		response = self.client.get(
			reverse("coa:verify_coa", kwargs={"token": self.coa.verification_token})
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.coa.coa_number)
		self.assertContains(response, "Authentic COA")
		self.assertContains(response, "Ready for Release")

	@override_settings(
		STORAGES={
			"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
			"staticfiles": {
				"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
			},
		}
	)
	def test_existing_qr_without_trailing_slash_still_verifies(self):
		response = self.client.get(f"/verify/{self.coa.verification_token}")

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.coa.coa_number)

	def test_invalid_verification_token_returns_404(self):
		response = self.client.get(reverse("coa:verify_coa", kwargs={"token": "invalid"}))

		self.assertEqual(response.status_code, 404)

	def test_generated_qr_url_uses_active_host(self):
		doc = build_coa_doc(self.coa, base_url="http://localhost:8000/")

		self.assertEqual(
			doc.verify_url,
			f"http://localhost:8000/verify/{self.coa.verification_token}/",
		)
