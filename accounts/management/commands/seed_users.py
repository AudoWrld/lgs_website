from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from accounts.models import Client
from branches.models import Branch
from branches.utils import to_title_case

User = get_user_model()

SEED_BRANCHES = [
    {
        "name": "Dar Es Salaam Main",
        "location": "Mikocheni, Dar es Salaam",
        "phone": "+255 222 701 234",
        "email": "daressalaam@lgs.co.tz",
    },
    {
        "name": "Arusha Branch",
        "location": "Njiro, Arusha",
        "phone": "+255 272 545 678",
        "email": "arusha@lgs.co.tz",
    },
    {
        "name": "Mwanza Branch",
        "location": "Nyamagana, Mwanza",
        "phone": "+255 282 500 123",
        "email": "mwanza@lgs.co.tz",
    },
]

SEED_PASSWORD = "passwd"

SEED_ROLES = [
    ("administrator", "create_administrator", "Samuel", "Mwangi"),
    ("customer", "create_user", "John", "Otieno"),
    ("reception", "create_reception", "Grace", "Wanjiru"),
    ("chemist", "create_chemist", "Peter", "Njoroge"),
    ("quantity_control", "create_quantity_control", "Mary", "Achieng"),
    ("accountant", "create_accountant", "David", "Ochieng"),
]

PHONE_BASE = 712000000


def build_email(role_key, branch):
    branch_slug = slugify(branch.name).replace("-", "_")
    return f"{role_key}.{branch_slug}@gmail.com"


def build_phone(branch_index, role_index):
    number = PHONE_BASE + branch_index * 100 + role_index
    return f"+255{number}"


class Command(BaseCommand):
    help = (
        "Seeds default branches and creates test users for every branch. "
        "Customer users receive individual client profiles. "
        "Development and testing use only."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0
        client_profiles_created = 0

        for entry in SEED_BRANCHES:
            name = to_title_case(entry["name"])
            details = {
                "location": entry["location"],
                "phone": entry["phone"],
                "email": entry["email"],
            }

            branch, created = Branch.objects.get_or_create(
                name=name,
                defaults={"is_active": True, **details},
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created branch: {branch.name}"))
                continue

            updated_fields = []

            for field, value in details.items():
                if not getattr(branch, field):
                    setattr(branch, field, value)
                    updated_fields.append(field)

            if updated_fields:
                branch.save(update_fields=[*updated_fields, "updated_at"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated branch: {branch.name} "
                        f"({', '.join(updated_fields)})"
                    )
                )

        branches = list(Branch.objects.order_by("pk"))

        for branch_index, branch in enumerate(branches):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nBranch: {branch.name}"))

            for role_index, (
                role_key,
                method,
                first_name,
                last_name,
            ) in enumerate(SEED_ROLES):
                email = build_email(role_key, branch)

                existing_user = User.objects.filter(email=email).first()

                if existing_user:
                    if role_key == "customer":
                        client_name = (
                            existing_user.get_full_name()
                            or existing_user.email.split("@")[0]
                        )

                        _, profile_created = Client.objects.get_or_create(
                            portal_user=existing_user,
                            defaults={
                                "client_type": Client.INDIVIDUAL,
                                "client_name": client_name,
                                "contact_person": client_name,
                                "email": existing_user.email,
                                "whatsapp_number": (existing_user.whatsapp_number),
                                "registered_by": existing_user.created_by,
                            },
                        )

                        if profile_created:
                            client_profiles_created += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Created individual client profile: "
                                    f"{existing_user.email}"
                                )
                            )

                    self.stdout.write(
                        self.style.WARNING(f"Skipped (already exists): {email}")
                    )
                    skipped_count += 1
                    continue

                user = getattr(User.objects, method)(
                    email=email,
                    password=SEED_PASSWORD,
                    first_name=first_name,
                    last_name=last_name,
                    whatsapp_number=build_phone(
                        branch_index,
                        role_index,
                    ),
                    branch=branch,
                )

                if role_key == "customer":
                    client_name = f"{first_name} {last_name}"

                    Client.objects.create(
                        portal_user=user,
                        client_type=Client.INDIVIDUAL,
                        client_name=client_name,
                        contact_person=client_name,
                        email=email,
                        whatsapp_number=user.whatsapp_number,
                    )

                    client_profiles_created += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created individual client profile: {email}"
                        )
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created: {email} - {user.get_full_name()} "
                        f"({user.get_role_display()})"
                    )
                )
                created_count += 1

        for administrator in User.objects.filter(
            role=User.ADMINISTRATOR,
            email__startswith="administrator.",
        ):
            has_admin_access = administrator.is_administrator and administrator.is_staff
            style = self.style.SUCCESS if has_admin_access else self.style.ERROR
            self.stdout.write(
                style(f"{administrator.email} has admin access: " f"{has_admin_access}")
            )

        for accountant in User.objects.filter(
            role=User.ACCOUNTANT,
            email__startswith="accountant.",
        ):
            can_release = accountant.has_perm("coa.authorize_release")
            style = self.style.SUCCESS if can_release else self.style.ERROR
            self.stdout.write(
                style(f"{accountant.email} can authorize release: " f"{can_release}")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(branches)} branches, "
                f"{created_count} users created, "
                f"{client_profiles_created} client profiles created, "
                f"{skipped_count} users skipped."
            )
        )
