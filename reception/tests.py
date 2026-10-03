from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client, User
from payments.forms import PaymentUpdateForm
from payments.models import Payment
from samples.models import Sample, SampleService, Service
from submissions.models import Submission


class SubmissionConfirmationRedirectTests(TestCase):
    def test_submit_confirmation_redirects_to_coa_reporting_preference(self):
        reception_user = User.objects.create_reception(
            email="reception@example.com",
            password="Password123!",
        )
        self.client.force_login(reception_user)

        client = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Acme Labs",
            contact_person="Jane Doe",
            email="client@example.com",
            whatsapp_number="123456789",
            registered_by=reception_user,
        )
        submission = Submission.objects.create(client=client, registered_by=reception_user)
        sample = Sample.objects.create(
            submission=submission,
            client_sample_id="SAMPLE-001",
            sample_type=Sample.ROCK,
            added_by=reception_user,
        )
        service = Service.objects.create(
            name="Assay Service",
            method_of_analysis="AAS",
            pricing_type=Service.FIXED,
            unit_price="150.00",
        )
        SampleService.objects.create(sample=sample, service=service)

        response = self.client.post(
            reverse("reception:submission_confirm_submit", args=[submission.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("reception:coa_reporting_preference", args=[submission.reference]),
        )


class WorksheetListOrderingTests(TestCase):
    def test_worksheet_generation_lists_most_recently_submitted_first(self):
        reception_user = User.objects.create_reception(
            email="reception2@example.com",
            password="Password123!",
        )
        self.client.force_login(reception_user)

        first_client = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Older Client",
            contact_person="Old User",
            email="older@example.com",
            whatsapp_number="111111111",
            registered_by=reception_user,
        )
        second_client = Client.objects.create(
            client_type=Client.INDIVIDUAL,
            client_name="Newer Client",
            contact_person="New User",
            email="newer@example.com",
            whatsapp_number="222222222",
            registered_by=reception_user,
        )

        older = Submission.objects.create(
            client=first_client,
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now() - timezone.timedelta(days=2),
        )
        newer = Submission.objects.create(
            client=second_client,
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now(),
        )

        response = self.client.get(reverse("reception:worksheet_generation"))

        self.assertEqual(list(response.context["submissions"][:2]), [newer, older])

    def test_client_submission_form_lists_most_recently_submitted_first(self):
        reception_user = User.objects.create_reception(
            email="reception3@example.com",
            password="Password123!",
        )
        self.client.force_login(reception_user)

        older = Submission.objects.create(
            client=Client.objects.create(
                client_type=Client.INDIVIDUAL,
                client_name="Older Client",
                contact_person="Old User",
                email="older2@example.com",
                whatsapp_number="333333333",
                registered_by=reception_user,
            ),
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now() - timezone.timedelta(days=3),
        )
        newer = Submission.objects.create(
            client=Client.objects.create(
                client_type=Client.INDIVIDUAL,
                client_name="Newer Client",
                contact_person="New User",
                email="newer2@example.com",
                whatsapp_number="444444444",
                registered_by=reception_user,
            ),
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now(),
        )

        response = self.client.get(reverse("reception:client_submission_form"))

        self.assertEqual(list(response.context["submissions"][:2]), [newer, older])

    def test_payment_details_lists_most_recently_submitted_first(self):
        reception_user = User.objects.create_reception(
            email="reception4@example.com",
            password="Password123!",
        )
        self.client.force_login(reception_user)

        older = Submission.objects.create(
            client=Client.objects.create(
                client_type=Client.INDIVIDUAL,
                client_name="Older Payment Client",
                contact_person="Old User",
                email="olderpay@example.com",
                whatsapp_number="555555555",
                registered_by=reception_user,
            ),
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now() - timezone.timedelta(days=5),
        )
        newer = Submission.objects.create(
            client=Client.objects.create(
                client_type=Client.INDIVIDUAL,
                client_name="Newer Payment Client",
                contact_person="New User",
                email="newerpay@example.com",
                whatsapp_number="666666666",
                registered_by=reception_user,
            ),
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now(),
        )

        response = self.client.get(reverse("reception:payment_details"))

        self.assertEqual(list(response.context["submissions"][:2]), [newer, older])

    def test_payment_status_updates_from_paid_amount(self):
        reception_user = User.objects.create_reception(
            email="reception5@example.com",
            password="Password123!",
        )
        self.client.force_login(reception_user)

        submission = Submission.objects.create(
            client=Client.objects.create(
                client_type=Client.INDIVIDUAL,
                client_name="Auto Status Client",
                contact_person="Auto User",
                email="autostatus@example.com",
                whatsapp_number="777777777",
                registered_by=reception_user,
            ),
            registered_by=reception_user,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        payment = Payment.objects.create(
            submission=submission,
            gross_amount="1000.00",
            discount="0.00",
            total_amount_paid="0.00",
            payment_status=Payment.UNPAID,
        )

        response = self.client.post(
            f"{reverse('reception:payment_details')}?ref={submission.reference}",
            {
                "additional_amount_paid": "500.00",
                "discount": "0.00",
                "payment_method": Payment.CASH,
                "transaction_reference": "",
                "payment_status": Payment.UNPAID,
                "remarks": "",
            },
        )

        payment.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payment.payment_status, Payment.PARTIALLY_PAID)
        self.assertEqual(payment.total_amount_paid, Decimal("500.00"))

    def test_payment_status_field_is_read_only(self):
        form = PaymentUpdateForm()
        self.assertTrue(form.fields["payment_status"].disabled)
        self.assertEqual(form.fields["payment_status"].widget.attrs.get("disabled"), "disabled")
