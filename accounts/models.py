from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.CUSTOMER)
        return self._create_user(email, password, **extra_fields)

    def create_customer(self, email, password=None, created_by=None, **extra_fields):
        if created_by is not None and not created_by.is_reception:
            raise PermissionDenied(
                "Only Reception may register client portal accounts."
            )

        extra_fields["role"] = User.CUSTOMER
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_reception(self, email, password=None, **extra_fields):
        extra_fields["role"] = User.RECEPTION
        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.ADMINISTRATOR)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("role") in (User.CUSTOMER, User.RECEPTION):
            raise ValueError("A superuser cannot hold the Customer or Reception role.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):

    CUSTOMER = "CUSTOMER"
    RECEPTION = "RECEPTION"
    ADMINISTRATOR = "ADMINISTRATOR"

    ROLE_CHOICES = [
        (CUSTOMER, "Customer"),
        (RECEPTION, "Reception"),
        (ADMINISTRATOR, "Administrator"),
    ]

    username = None
    email = models.EmailField(unique=True, db_index=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=CUSTOMER,
        db_index=True,
    )

    whatsapp_number = models.CharField(max_length=30, blank=True, db_index=True)

    must_change_password = models.BooleanField(
        default=False,
        help_text="Set when Reception issues a temporary password on the Client Submission Form.",
    )

    created_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts_created",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"

    @property
    def is_customer(self):
        return self.role == self.CUSTOMER

    @property
    def is_reception(self):
        return self.role == self.RECEPTION

    @property
    def is_administrator(self):
        return self.role == self.ADMINISTRATOR

    def clean(self):
        super().clean()
        if self.role in (self.CUSTOMER, self.RECEPTION) and (
            self.is_staff or self.is_superuser
        ):
            raise ValidationError(
                "Customer and Reception accounts cannot be granted admin-site access."
            )

    def save(self, *args, **kwargs):
        if self.role in (self.CUSTOMER, self.RECEPTION):
            self.is_staff = False
            self.is_superuser = False
        super().save(*args, **kwargs)

    def can_register(self, role):
        if self.is_reception:
            return role == self.CUSTOMER
        if self.is_administrator or self.is_superuser:
            return role in (self.CUSTOMER, self.RECEPTION, self.ADMINISTRATOR)
        return False


class Client(models.Model):
    INDIVIDUAL = "INDIVIDUAL"
    COMPANY = "COMPANY"

    CLIENT_TYPE_CHOICES = [
        (INDIVIDUAL, "Individual"),
        (COMPANY, "Company"),
    ]

    portal_user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="client_profile",
        limit_choices_to={"role": User.CUSTOMER},
        null=True,
        blank=True,
        help_text="The read-only LGS Results Portal account generated for this client.",
    )

    client_type = models.CharField(max_length=20, choices=CLIENT_TYPE_CHOICES)
    client_name = models.CharField(max_length=200, db_index=True)
    contact_person = models.CharField(max_length=150, db_index=True)
    email = models.EmailField(db_index=True)
    whatsapp_number = models.CharField(max_length=30, db_index=True)

    registered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_registered",
        limit_choices_to={"role": User.RECEPTION},
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client_name"]
        indexes = [
            models.Index(fields=["client_name", "email"]),
        ]

    def __str__(self):
        return f"{self.client_name} - {self.contact_person}"

    @classmethod
    def find_possible_duplicates(
        cls, client_name, email, whatsapp_number, exclude_pk=None
    ):
        queryset = cls.objects.filter(
            models.Q(client_name__iexact=client_name.strip())
            | models.Q(email__iexact=email.strip())
            | models.Q(whatsapp_number=whatsapp_number.strip())
        )
        if exclude_pk:
            queryset = queryset.exclude(pk=exclude_pk)
        return queryset


class ClientEditLog(models.Model):
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="edit_logs"
    )
    edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_edits",
        limit_choices_to={"role": User.RECEPTION},
    )

    previous_client_type = models.CharField(max_length=20, blank=True)
    previous_client_name = models.CharField(max_length=200, blank=True)
    previous_contact_person = models.CharField(max_length=150, blank=True)
    previous_email = models.EmailField(blank=True)
    previous_whatsapp_number = models.CharField(max_length=30, blank=True)

    edited_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-edited_at"]
        verbose_name = "Client Edit Log"
        verbose_name_plural = "Client Edit Logs"

    def __str__(self):
        return f"{self.client.client_name} edited {self.edited_at:%Y-%m-%d %H:%M}"
