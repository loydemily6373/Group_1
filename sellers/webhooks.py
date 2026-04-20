import json
import logging
import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_order_webhook(order_item):
    """
    Send a webhook notification to the seller when an order item is placed.
    Also creates an in-app notification.
    
    Args:
        order_item: The OrderItem instance that was just created
    """
    try:
        from .models import WebhookURL, Notification
        
        # Create an in-app notification
        Notification.objects.create(
            seller=order_item.seller,
            order_number=order_item.order.order_number,
            product_name=order_item.product_name,
            quantity=order_item.quantity,
            is_seen=False
        )
        
        # Get the seller's webhook URL if it exists and is active
        webhook_config = WebhookURL.objects.filter(
            seller=order_item.seller,
            is_active=True
        ).first()
        
        if not webhook_config:
            logger.info(f"No active webhook found for seller {order_item.seller.username}")
            return False
        
        # Prepare the webhook payload
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
        
        # Send the webhook
        response = requests.post(
            webhook_config.webhook_url,
            json=payload,
            timeout=10,
            headers={'Content-Type': 'application/json'},
        )
        
        # Log the result
        if response.status_code in [200, 201, 202, 204]:
            logger.info(f"Webhook sent successfully to {order_item.seller.username}: {response.status_code}")
            return True
        else:
            logger.warning(f"Webhook failed for {order_item.seller.username}: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send webhook: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending webhook: {str(e)}")
        return False
