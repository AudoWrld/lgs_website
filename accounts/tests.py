from django.test import TestCase
from django.core.management import call_command

from accounts.models import Client, User
from accounts.forms import ClientForm


class ClientFormNameTests(TestCase):
    def test_registration_title_cases_client_name_and_contact_person(self):
        form = ClientForm(
            data={
                "client_type": Client.COMPANY,
                "client_name": "jane doe mining ltd",
                "contact_person": "john smith",
                "email": "jane@example.com",
                "whatsapp_number": "0712345678",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_name"], "Jane Doe Mining Ltd")
        self.assertEqual(form.cleaned_data["contact_person"], "John Smith")

    def test_edit_preserves_existing_client_name_case(self):
        reception = User.objects.create_reception(
            email="reception@example.com", password="TestPass123!"
        )
        client = Client.objects.create(
            client_type=Client.COMPANY,
            client_name="ABC Mining Ltd",
            contact_person="Jane Doe",
            email="abc@example.com",
            whatsapp_number="+255712345678",
            registered_by=reception,
        )
        form = ClientForm(
            data={
                "client_type": Client.COMPANY,
                "client_name": client.client_name,
                "contact_person": client.contact_person,
                "email": client.email,
                "whatsapp_number": client.whatsapp_number,
            },
            instance=client,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_name"], "ABC Mining Ltd")
        self.assertEqual(form.cleaned_data["contact_person"], "Jane Doe")


class AccountantRoleTests(TestCase):
    def test_accountant_manager_sets_non_admin_staff_role(self):
        user = User.objects.create_accountant(
            email="accountant-role@example.com",
            password="TestPass123!",
        )

        self.assertEqual(user.role, User.ACCOUNTANT)
        self.assertTrue(user.is_accountant)
        self.assertTrue(user.is_staff_role)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_seed_users_creates_accountant(self):
        call_command("seed_users", verbosity=0)

        user = User.objects.get(email="accountant@gmail.com")
        self.assertEqual(user.role, User.ACCOUNTANT)

    def test_accountant_login_redirects_to_accountant_workspace(self):
        user = User.objects.create_accountant(
            email="accountant-login@example.com",
            password="TestPass123!",
        )
        self.client.force_login(user)

        response = self.client.get("/accounts/post-login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accountant/dashboard/")
