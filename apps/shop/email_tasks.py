"""
Celery tasks for shop/order email sending.
All email operations are offloaded to background workers.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='shop.send_order_confirmation_email',
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def send_order_confirmation_email_task(self, cart_id, payment_id):
    """
    Send order confirmation email.
    
    Args:
        cart_id: EventCart UUID
        payment_id: ProductPayment UUID
    """
    try:
        from apps.shop.models.shop_models import EventCart
        from apps.shop.models.payments import ProductPayment
        from apps.shop.email_utils import send_order_confirmation_email
        
        cart = EventCart.objects.get(id=cart_id)
        payment = ProductPayment.objects.get(id=payment_id)
        result = send_order_confirmation_email(cart, payment)
        
        if result:
            logger.info(f"Order confirmation email sent for cart {cart_id}")
        else:
            logger.warning(f"Failed to send order confirmation for cart {cart_id}")
            
        return result
        
    except (EventCart.DoesNotExist, ProductPayment.DoesNotExist) as e:
        logger.error(f"Cart or Payment not found: {e}")
        return False
    except Exception as exc:
        logger.error(f"Error sending order confirmation: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_payment_verified_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_payment_verified_email_task(self, cart_id, payment_id):
    """Send payment verification email."""
    try:
        from apps.shop.models.shop_models import EventCart
        from apps.shop.models.payments import ProductPayment
        from apps.shop.email_utils import send_payment_verified_email
        
        cart = EventCart.objects.get(id=cart_id)
        payment = ProductPayment.objects.get(id=payment_id)
        result = send_payment_verified_email(cart, payment)
        
        if result:
            logger.info(f"Payment verified email sent for cart {cart_id}")
        else:
            logger.warning(f"Failed to send payment verified email for cart {cart_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending payment verified email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_order_update_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_order_update_email_task(self, cart_id, order_id, updated_fields):
    """Send email when admin updates order."""
    try:
        from apps.shop.models.shop_models import EventCart, EventProductOrder
        from apps.shop.email_utils import send_order_update_email
        
        cart = EventCart.objects.get(id=cart_id)
        order = EventProductOrder.objects.get(id=order_id)
        result = send_order_update_email(cart, order, updated_fields)
        
        if result:
            logger.info(f"Order update email sent for order {order_id}")
        else:
            logger.warning(f"Failed to send order update email for order {order_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending order update email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_cart_created_by_admin_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_cart_created_by_admin_email_task(self, cart_id):
    """Send email when admin creates cart on behalf of user."""
    try:
        from apps.shop.models.shop_models import EventCart
        from apps.shop.email_utils import send_cart_created_by_admin_email
        
        cart = EventCart.objects.get(id=cart_id)
        result = send_cart_created_by_admin_email(cart)
        
        if result:
            logger.info(f"Cart created by admin email sent for cart {cart_id}")
        else:
            logger.warning(f"Failed to send cart created email for cart {cart_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending cart created email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_order_refund_created_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_order_refund_created_email_task(self, refund_id):
    """Send email when order refund is created."""
    try:
        from apps.shop.models.payments import OrderRefund
        from apps.shop.email_utils import send_order_refund_created_email
        
        refund = OrderRefund.objects.get(id=refund_id)
        result = send_order_refund_created_email(refund)
        
        if result:
            logger.info(f"Order refund created email sent for refund {refund_id}")
        else:
            logger.warning(f"Failed to send refund created email for refund {refund_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending refund created email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_order_refund_processed_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_order_refund_processed_email_task(self, refund_id):
    """Send email when order refund is processed."""
    try:
        from apps.shop.models.payments import OrderRefund
        from apps.shop.email_utils import send_order_refund_processed_email
        
        refund = OrderRefund.objects.get(id=refund_id)
        result = send_order_refund_processed_email(refund)
        
        if result:
            logger.info(f"Order refund processed email sent for refund {refund_id}")
        else:
            logger.warning(f"Failed to send refund processed email for refund {refund_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending refund processed email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='shop.send_order_refund_failed_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_order_refund_failed_email_task(self, refund_id):
    """Send email when order refund fails."""
    try:
        from apps.shop.models.payments import OrderRefund
        from apps.shop.email_utils import send_order_refund_failed_email
        
        refund = OrderRefund.objects.get(id=refund_id)
        result = send_order_refund_failed_email(refund)
        
        if result:
            logger.info(f"Order refund failed email sent for refund {refund_id}")
        else:
            logger.warning(f"Failed to send refund failed email for refund {refund_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending refund failed email: {exc}")
        raise self.retry(exc=exc)
