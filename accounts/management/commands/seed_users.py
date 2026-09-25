from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

SEED_USERS = [
    {
        "email": "customer@gmail.com",
        "phone": "+255712483951",
        "first_name": "John",
        "last_name": "Otieno",
        "creator": lambda: User.objects.create_user(
            email="customer@gmail.com",
            password="passwd",
            first_name="John",
            last_name="Otieno",
            whatsapp_number="+255712483951",
        ),
    },
    {
        "email": "reception@gmail.com",
        "phone": "+255754629183",
        "first_name": "Grace",
        "last_name": "Wanjiru",
        "creator": lambda: User.objects.create_reception(
            email="reception@gmail.com",
            password="passwd",
            first_name="Grace",
            last_name="Wanjiru",
            whatsapp_number="+255754629183",
        ),
    },
    {
        "email": "chemist@gmail.com",
        "phone": "+255713857426",
        "first_name": "Peter",
        "last_name": "Njoroge",
        "creator": lambda: User.objects.create_chemist(
            email="chemist@gmail.com",
            password="passwd",
            first_name="Peter",
            last_name="Njoroge",
            whatsapp_number="+255713857426",
        ),
    },
    {
        "email": "quantity_control@gmail.com",
        "phone": "+255765291847",
        "first_name": "Mary",
        "last_name": "Achieng",
        "creator": lambda: User.objects.create_quantity_control(
            email="quantity_control@gmail.com",
            password="passwd",
            first_name="Mary",
            last_name="Achieng",
            whatsapp_number="+255765291847",
        ),
    },
]


class Command(BaseCommand):
    help = (
        "Seeds one test user per role (customer, reception, chemist, "
        "quantity_control), all with password 'passwd'. Development/testing "
        "use only — never run against a production database."
    )

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0

        for entry in SEED_USERS:
            if User.objects.filter(email=entry["email"]).exists():
                self.stdout.write(
                    self.style.WARNING(f"Skipped (already exists): {entry['email']}")
                )
                skipped_count += 1
                continue

            user = entry["creator"]()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created: {entry['email']} — {user.get_full_name()} ({user.get_role_display()})"
                )
            )
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"\n{created_count} created, {skipped_count} skipped.")
        )
