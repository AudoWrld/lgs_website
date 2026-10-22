from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from branches.models import Branch
from branches.utils import to_title_case

User = get_user_model()

SEED_BRANCHES = [
    "Dar Es Salaam Main",
    "Arusha Branch",
    "Mwanza Branch",
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
        "Seeds the default branches, then creates one test user per role "
        "(administrator, customer, reception, chemist, quantity_control, "
        "accountant) for every branch in the database, all with password "
        "'passwd'. Development/testing use only — never run against a "
        "production database."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0

        for name in SEED_BRANCHES:
            branch, created = Branch.objects.get_or_create(
                name=to_title_case(name),
                defaults={"is_active": True},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created branch: {branch.name}"))

        branches = list(Branch.objects.order_by("pk"))

        for branch_index, branch in enumerate(branches):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nBranch: {branch.name}"))

            for role_index, (role_key, method, first_name, last_name) in enumerate(
                SEED_ROLES
            ):
                email = build_email(role_key, branch)

                if User.objects.filter(email=email).exists():
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
                    whatsapp_number=build_phone(branch_index, role_index),
                    branch=branch,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created: {email} — {user.get_full_name()} "
                        f"({user.get_role_display()})"
                    )
                )
                created_count += 1

        for administrator in User.objects.filter(
            role=User.ADMINISTRATOR, email__startswith="administrator."
        ):
            has_admin_access = administrator.is_administrator and administrator.is_staff
            style = self.style.SUCCESS if has_admin_access else self.style.ERROR
            self.stdout.write(
                style(f"{administrator.email} has admin access: {has_admin_access}")
            )

        for accountant in User.objects.filter(
            role=User.ACCOUNTANT, email__startswith="accountant."
        ):
            can_release = accountant.has_perm("coa.authorize_release")
            style = self.style.SUCCESS if can_release else self.style.ERROR
            self.stdout.write(
                style(f"{accountant.email} can authorize release: {can_release}")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(branches)} branches, {created_count} users created, "
                f"{skipped_count} skipped."
            )
        )
