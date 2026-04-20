from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import User
from .models import WebhookURL


@receiver(post_save, sender=User)
def create_webhook_for_seller(sender, instance, created, **kwargs):
    """
    Create a webhook URL when a new seller account is created.
    """
    if created and instance.role == 'seller':
        # Only create if webhook doesn't already exist
        if not WebhookURL.objects.filter(seller=instance).exists():
            webhook_url = WebhookURL.generate_unique_webhook_url(instance)
            WebhookURL.objects.create(
                seller=instance,
                webhook_url=webhook_url,
                is_active=True
            )
