from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Client, User
from coa.models import COA
from payments.models import Payment
from samples.models import Sample
from submissions.models import Submission
from quantity_control.views import _is_editable


class QCReviewLockTests(TestCase):
	def test_pending_sample_is_editable(self):
		sample = Sample(analysis_status=Sample.SUBMITTED_TO_QC)

		self.assertTrue(_is_editable(sample, object()))

	def test_qc_approved_sample_is_not_editable(self):
		sample = Sample(analysis_status=Sample.QC_APPROVED)

		self.assertFalse(_is_editable(sample, object()))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class GenerateReportPageTests(TestCase):
	def test_generate_report_route_returns_html(self):
		user = User.objects.create_quantity_control(email="qc@example.com")
		self.client.force_login(user)

		response = self.client.get(reverse("qc:generate_report"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Generate Report")

	def test_dashboard_counts_generated_coas(self):
		user = User.objects.create_quantity_control(email="qc-dashboard@example.com")
		self.client.force_login(user)
		client_record = Client.objects.create(
			client_type=Client.INDIVIDUAL,
			client_name="Dashboard Client",
			contact_person="Test Contact",
			email="dashboard-client@example.com",
			whatsapp_number="123456789",
		)
		submission = Submission.objects.create(client=client_record, is_submitted=True)
		COA.objects.create(submission=submission, coa_number="LGS-TEST-001")

		response = self.client.get(reverse("qc:qc_dashboard"))

		self.assertEqual(response.context["generated_coa_count"], 1)
		self.assertContains(response, "Generated COAs")


class ReportDetailCOATests(TestCase):
	def setUp(self):
		self.media_dir = TemporaryDirectory()
		self.addCleanup(self.media_dir.cleanup)
		self.storage_settings = override_settings(
			MEDIA_ROOT=self.media_dir.name,
			STORAGES={
				"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
				"staticfiles": {
					"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
				},
			},
		)
		self.storage_settings.enable()
		self.addCleanup(self.storage_settings.disable)

		user = User.objects.create_quantity_control(email="qc-coa-detail@example.com")
		client_record = Client.objects.create(
			client_type=Client.INDIVIDUAL,
			client_name="QC COA Client",
			contact_person="Test Contact",
			email="qc-coa-client@example.com",
			whatsapp_number="123456789",
		)
		self.submission = Submission.objects.create(
			client=client_record,
			is_submitted=True,
		)
		Payment.objects.create(
			submission=self.submission,
			gross_amount="100.00",
			total_amount_paid="0.00",
		)
		self.client.force_login(user)

	def _create_png(self):
		image = Image.new("RGB", (40, 40), "red")
		for x in range(20, 40):
			for y in range(40):
				image.putpixel((x, y), (0, 0, 255))
		output = BytesIO()
		image.save(output, format="PNG")
		return output.getvalue()

	def _create_coa(self, coa_status):
		coa = COA.objects.create(
			submission=self.submission,
			coa_number=f"{self.submission.reference}-01",
			status=coa_status,
		)
		coa.png_file.save("coa.png", ContentFile(self._create_png()), save=True)
		return coa

	def test_pending_coa_is_blurred_without_file_actions_or_original_url(self):
		coa = self._create_coa(COA.PAYMENT_PENDING)
		page = self.client.get(
			reverse("qc:report_detail", args=[self.submission.reference])
		)
		preview = self.client.get(
			reverse("qc:report_coa_preview", args=[coa.pk])
		)

		self.assertContains(page, "is-blurred")
		self.assertContains(page, "Available after payment")
		self.assertNotContains(page, "Download PDF")
		self.assertNotContains(page, "Download PNG")
		self.assertNotContains(page, coa.png_file.url)
		self.assertEqual(preview.status_code, 200)
		self.assertEqual(preview["Content-Type"], "image/png")
		with coa.png_file.open("rb") as source:
			self.assertNotEqual(preview.content, source.read())

	def test_ready_coa_preview_is_clear_but_has_no_download_actions(self):
		coa = self._create_coa(COA.READY_FOR_RELEASE)
		page = self.client.get(
			reverse("qc:report_detail", args=[self.submission.reference])
		)
		preview = self.client.get(
			reverse("qc:report_coa_preview", args=[coa.pk])
		)

		self.assertNotContains(page, "is-blurred")
		self.assertNotContains(page, "Download PDF")
		self.assertNotContains(page, "Download PNG")
		self.assertEqual(preview.status_code, 200)
		with coa.png_file.open("rb") as source:
			self.assertEqual(b"".join(preview.streaming_content), source.read())
