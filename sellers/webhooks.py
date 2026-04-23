import json
import logging
import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_order_webhook(order_item):
    """
    Send a webhook notification to the seller when an order item is placed.
    Also creates an in-app notification AND sends to Slack.
    """
    try:
        from .models import WebhookURL, Notification
        
        # 1. Create in-app notification (you already have this)
        Notification.objects.create(
            seller=order_item.seller,
            order_number=order_item.order.order_number,
            product_name=order_item.product_name,
            quantity=order_item.quantity,
            is_seen=False
        )
        
        # 2. Send to external seller webhook (if they have one configured)
        webhook_config = WebhookURL.objects.filter(
            seller=order_item.seller,
            is_active=True
        ).first()
        
        if webhook_config:
            payload = {
                'event': 'order_placed',
                'order_number': order_item.order.order_number,
                'product_name': order_item.product_name,
                'quantity': order_item.quantity,
                'unit_price': str(order_item.unit_price),
                'line_total': str(order_item.line_total),
                'shipping_address': {
                    'recipient_name': order_item.order.buyer_shipping_address.recipient_name,
                    'address_line_1': order_item.order.buyer_shipping_address.address_line_1,
                    'address_line_2': order_item.order.buyer_shipping_address.address_line_2,
                    'city': order_item.order.buyer_shipping_address.city,
                    'state': order_item.order.buyer_shipping_address.state,
                    'postal_code': order_item.order.buyer_shipping_address.postal_code,
                    'country': order_item.order.buyer_shipping_address.country,
                    'phone_number': order_item.order.buyer_shipping_address.phone_number,
                },
                'order_date': order_item.order.created_at.isoformat(),
                'timestamp': timezone.now().isoformat(),
            }
            
            response = requests.post(
                webhook_config.webhook_url,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'},
            )
            
            if response.status_code in [200, 201, 202, 204]:
                logger.info(f"Webhook sent successfully to {order_item.seller.username}")
            else:
                logger.warning(f"Webhook failed for {order_item.seller.username}: {response.status_code}")

        return True

    except Exception as e:
        logger.error(f"Unexpected error sending webhook: {str(e)}")
        return False


