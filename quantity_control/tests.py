from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Client, User
from coa.models import COA
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
