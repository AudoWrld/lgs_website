from datetime import timedelta
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from quotations.models import Quotation, QuotationItem


class QuotationItemModelTest(TestCase):
    def test_service_title_case(self):
        """Service should be saved in Title Case."""
        item = QuotationItem.objects.create(
            service="analysis of gold & copper",
            description="fire assay method",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item.service, "Analysis Of Gold & Copper")

    def test_description_capitalize_first(self):
        """Description should have only the first character capitalized."""
        item = QuotationItem.objects.create(
            service="Test Service",
            description="fire assay method",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item.description, "Fire assay method")

    def test_service_acronym_preserved(self):
        """Acronyms like ICP-OES should stay intact."""
        item = QuotationItem.objects.create(
            service="icp-oes analysis",
            description="test",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item.service, "Icp-Oes Analysis")
        # Test with uppercase input
        item2 = QuotationItem.objects.create(
            service="ICP-OES",
            description="test",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item2.service, "ICP-OES")

    def test_description_empty_stays_empty(self):
        """Empty description should stay empty."""
        item = QuotationItem.objects.create(
            service="Test Service",
            description="",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item.description, "")

    def test_description_extra_spaces_stripped(self):
        """Extra spaces should be stripped and collapsed."""
        item = QuotationItem.objects.create(
            service="Test Service",
            description="  hello   world  ",
            quantity=1,
            unit_price=100
        )
        self.assertEqual(item.description, "Hello world")


class QuotationModelTest(TestCase):
    def test_is_expired_property(self):
        """is_expired should return True if expired_at is not None."""
        quotation = Quotation.objects.create(
            quotation_date=timezone.localdate(),
            valid_until=timezone.localdate() + timedelta(days=10)
        )
        self.assertFalse(quotation.is_expired)
        quotation.expired_at = timezone.now()
        quotation.save()
        self.assertTrue(quotation.is_expired)


class ExpireQuotationsCommandTest(TestCase):
    def setUp(self):
        today = timezone.localdate()
        # Create a quotation that is past valid_until
        self.past_quotation = Quotation.objects.create(
            quotation_date=today - timedelta(days=20),
            valid_until=today - timedelta(days=10)  # 10 days ago
        )
        # Create a quotation that is valid today (valid_until == today)
        self.valid_today_quotation = Quotation.objects.create(
            quotation_date=today - timedelta(days=5),
            valid_until=today
        )
        # Create a quotation that is valid in the future
        self.future_quotation = Quotation.objects.create(
            quotation_date=today - timedelta(days=5),
            valid_until=today + timedelta(days=10)
        )
        # Create an already expired quotation (with expired_at set in the past)
        self.already_expired = Quotation.objects.create(
            quotation_date=today - timedelta(days=20),
            valid_until=today - timedelta(days=15),
            expired_at=timezone.now() - timedelta(days=5)
        )

    def test_past_valid_until_gets_expired_at(self):
        """Quotation with valid_until < today should get expired_at set."""
        # Call the command
        call_command('expire_quotations')
        # Refresh from db
        self.past_quotation.refresh_from_db()
        self.assertIsNotNone(self.past_quotation.expired_at)

    def test_valid_until_equal_today_not_expired(self):
        """Quotation with valid_until == today should NOT get expired_at."""
        call_command('expire_quotations')
        self.valid_today_quotation.refresh_from_db()
        self.assertIsNone(self.valid_today_quotation.expired_at)

    def test_future_valid_until_not_expired(self):
        """Quotation with valid_until > today should not get expired_at."""
        call_command('expire_quotations')
        self.future_quotation.refresh_from_db()
        self.assertIsNone(self.future_quotation.expired_at)

    def test_already_expired_keeps_original_timestamp(self):
        """Already expired rows should keep their original expired_at."""
        old_expired_at = self.already_expired.expired_at
        call_command('expire_quotations')
        self.already_expired.refresh_from_db()
        self.assertEqual(self.already_expired.expired_at, old_expired_at)

    def test_dry_run_does_not_change_anything(self):
        """--dry-run should not change any expired_at."""
        call_command('expire_quotations', dry_run=True)
        self.past_quotation.refresh_from_db()
        self.assertIsNone(self.past_quotation.expired_at)

    def test_as_of_option(self):
        """--as-of should treat the given date as today."""
        # Set as_of to yesterday
        yesterday = timezone.localdate() - timedelta(days=1)
        # The past_quotation has valid_until = today - 10 days, which is < yesterday? Let's compute:
        # today - 10 days is less than yesterday (today - 1) if 10 > 1, which is true.
        # So past_quotation should be expired as of yesterday.
        # The valid_today_quotation has valid_until = today, which is > yesterday, so not expired as of yesterday.
        call_command('expire_quotations', as_of=yesterday.strftime("%Y-%m-%d"))
        self.past_quotation.refresh_from_db()
        self.valid_today_quotation.refresh_from_db()
        self.assertIsNotNone(self.past_quotation.expired_at)
        self.assertIsNone(self.valid_today_quotation.expired_at)
