from django.test import TestCase

from samples.models import Sample
from quantity_control.views import _is_editable


class QCReviewLockTests(TestCase):
	def test_pending_sample_is_editable(self):
		sample = Sample(analysis_status=Sample.SUBMITTED_TO_QC)

		self.assertTrue(_is_editable(sample, object()))

	def test_qc_approved_sample_is_not_editable(self):
		sample = Sample(analysis_status=Sample.QC_APPROVED)

		self.assertFalse(_is_editable(sample, object()))
