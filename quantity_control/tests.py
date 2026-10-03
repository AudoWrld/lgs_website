from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from samples.models import Sample
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
