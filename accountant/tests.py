from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User


@override_settings(
	STORAGES={
		"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
		"staticfiles": {
			"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
		},
	}
)
class AccountantPageTests(TestCase):
	def setUp(self):
		user = User.objects.create_accountant(email="accountant-ui@example.com")
		self.client.force_login(user)

	def test_navigation_pages_render_with_the_accountant_shell(self):
		pages = (
			("dashboard", "Dashboard"),
			("reference_list", "References"),
			("payment_add", "Record Payment"),
			("payment_list", "Payments"),
			("receipt_list", "Receipts"),
			("expense_list", "Expenses"),
			("quotation_list", "Quotations"),
			("invoice_list", "Invoices"),
			("debt_credit", "Debt & Credit"),
			("release_queue", "Report Release"),
			("reports", "Reports"),
		)

		for route_name, heading in pages:
			with self.subTest(route_name=route_name):
				response = self.client.get(reverse(f"accountant:{route_name}"))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, heading.replace("&", "&amp;"))
				self.assertContains(response, "Accountant")
				self.assertContains(response, 'action="/accounts/logout/"')

	def test_current_navigation_link_is_marked_active(self):
		response = self.client.get(reverse("accountant:payment_list"))

		self.assertContains(
			response,
			'href="/accountant/payments/" class="active"',
			html=False,
		)

	def test_release_queue_link_is_hidden_without_permission(self):
		response = self.client.get(reverse("accountant:dashboard"))

		self.assertNotContains(response, "Report Release")
