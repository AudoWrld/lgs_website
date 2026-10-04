from django.db.models.signals import post_save
from django.dispatch import receiver

from payments.models import Payment

from .services import release_if_paid


@receiver(post_save, sender=Payment)
def release_coas_when_paid(sender, instance, **kwargs):
    release_if_paid(instance.submission)
