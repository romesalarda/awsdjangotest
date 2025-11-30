"""
Order Refund Service
Handles automatic and manual refund processing for merchandise orders with robust error handling.
"""
import stripe
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from apps.shop.models import OrderRefund, ProductPayment, EventCart
from apps.shop.stripe_service import StripePaymentService

logger = logging.getLogger(__name__)

# Initialize Stripe
STRIPE_TEST_MODE = getattr(settings, 'STRIPE_TEST_MODE', True)
STRIPE_SECRET_KEY = getattr(settings, 'STRIPE_SECRET_KEY_TEST' if STRIPE_TEST_MODE else 'STRIPE_SECRET_KEY_LIVE', None)
STRIPE_WEBHOOK_SECRET = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class OrderRefundService:
    """Service for processing order refunds through Stripe and managing refund workflow"""
    
    def __init__(self):
        self.stripe_service = StripePaymentService()
    
    def process_automatic_refund(self, refund):
        """
        Process automatic refund through Stripe.
        
        Args:
            refund: OrderRefund instance
            
        Returns:
            tuple: (success: bool, message: str)
        """
        # Validation checks
        can_process, message = refund.can_process_refund()
        if not can_process:
            logger.warning(f"Refund {refund.refund_reference} cannot be processed: {message}")
            return False, message
        
        if refund.status not in [OrderRefund.RefundStatus.PENDING, OrderRefund.RefundStatus.IN_PROGRESS]:
            logger.warning(f"Refund {refund.refund_reference} has invalid status: {refund.status}")
            return False, f"Refund is already {refund.status}"
        
        if not refund.is_automatic_refund:
            logger.warning(f"Refund {refund.refund_reference} is not configured for automatic processing")
            return False, "This refund is not configured for automatic processing"
        
        if not refund.stripe_payment_intent:
            logger.error(f"Refund {refund.refund_reference} missing Stripe payment intent")
            return False, "No Stripe payment intent found for this refund"
        
        try:
            # Update status to processing
            refund.status = OrderRefund.RefundStatus.IN_PROGRESS
            refund.save()
            logger.info(f"Processing automatic refund {refund.refund_reference} for £{refund.refund_amount}")
            
            # Calculate refund amount in cents
            refund_amount_cents = int(refund.refund_amount * 100)
            
            # Create refund in Stripe
            stripe_refund = stripe.Refund.create(
                payment_intent=refund.stripe_payment_intent,
                amount=refund_amount_cents,
                reason=self._map_refund_reason_to_stripe(refund.refund_reason),
                metadata={
                    'refund_id': str(refund.id),
                    'cart_id': str(refund.cart.uuid) if refund.cart else None,
                    'event_id': str(refund.event.id) if refund.event else None,
                    'event_code': refund.event.event_code if refund.event else None,
                    'refund_reference': refund.refund_reference
                }
            )
            
            # Update refund with Stripe information
            refund.stripe_refund_id = stripe_refund.id
            refund.refund_method = 'Stripe'
            refund.save()
            
            logger.info(f"⏳ Stripe refund {refund.refund_reference} initiated and marked as IN_PROGRESS. Awaiting manual verification.")
            return True, "Refund payment sent via Stripe. Please verify completion to finalize."
        
        except stripe.error.InvalidRequestError as e:
            refund.status = OrderRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.error(f"❌ Stripe invalid request for refund {refund.refund_reference}: {e}")
            return False, f"Stripe error: {str(e)}"
        
        except stripe.error.CardError as e:
            refund.status = OrderRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.error(f"❌ Stripe card error for refund {refund.refund_reference}: {e}")
            return False, f"Card error: {str(e)}"
        
        except Exception as e:
            refund.status = OrderRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.exception(f"❌ Unexpected error processing refund {refund.refund_reference}")
            return False, f"Unexpected error: {str(e)}"
    
    def process_manual_refund(self, refund, processor_notes=None):
        """
        Initiate manual refund processing (bank transfer, cash, etc.).
        Marks refund as in-progress and awaits manual completion.
        
        Args:
            refund: OrderRefund instance
            processor_notes: Optional notes about processing
            
        Returns:
            tuple: (success: bool, message: str)
        """
        can_process, message = refund.can_process_refund()
        if not can_process:
            logger.warning(f"Manual refund {refund.refund_reference} cannot be processed: {message}")
            return False, message
        
        if refund.status not in [OrderRefund.RefundStatus.PENDING]:
            logger.warning(f"Manual refund {refund.refund_reference} has invalid status: {refund.status}")
            return False, f"Refund is already {refund.status}"
        
        try:
            refund.status = OrderRefund.RefundStatus.IN_PROGRESS
            if processor_notes:
                refund.processing_notes = processor_notes
            refund.save()
            
            logger.info(f"⏳ Manual refund {refund.refund_reference} marked as in-progress")
            return True, "Manual refund payment sent. Please verify completion to finalize."
        
        except Exception as e:
            logger.exception(f"❌ Error initiating manual refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def complete_manual_refund(self, refund, processor_notes=None):
        """
        Mark manual refund as completed.
        
        Args:
            refund: OrderRefund instance
            processor_notes: Optional completion notes
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status == OrderRefund.RefundStatus.PROCESSED:
            return False, "Refund already processed"
        
        if refund.status != OrderRefund.RefundStatus.IN_PROGRESS:
            return False, "Refund must be in IN_PROGRESS status before completing"
        
        try:
            refund.status = OrderRefund.RefundStatus.PROCESSED
            refund.processed_at = timezone.now()
            if processor_notes:
                if refund.processing_notes:
                    refund.processing_notes += f"\n\n{processor_notes}"
                else:
                    refund.processing_notes = processor_notes
            refund.save()
            
            # Update cart and order statuses
            if refund.cart:
                refund.cart.cart_status = 'refunded'
                refund.cart.save()
                
                # Update all order items in the cart
                from apps.shop.models import EventProductOrder
                order_items = EventProductOrder.objects.filter(cart=refund.cart)
                order_items.update(
                    status=EventProductOrder.Status.REFUNDED,
                    refund_status='PROCESSED'
                )
                logger.info(f"Cart {refund.cart.order_reference_id} and {order_items.count()} items marked as refunded")
            
            # Restore stock
            if not refund.stock_restored:
                success, stock_message = refund.restore_stock()
                logger.info(f"Stock restoration for {refund.refund_reference}: {stock_message}")
            
            logger.info(f"✅ Manual refund {refund.refund_reference} completed")
            return True, "Manual refund marked as completed"
        
        except Exception as e:
            logger.exception(f"❌ Error completing manual refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def retry_failed_refund(self, refund):
        """
        Retry a failed refund.
        
        Args:
            refund: OrderRefund instance
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status != OrderRefund.RefundStatus.FAILED:
            return False, "Only failed refunds can be retried"
        
        try:
            # Reset status to pending
            refund.status = OrderRefund.RefundStatus.PENDING
            refund.stripe_failure_reason = None
            refund.save()
            
            logger.info(f"🔄 Retrying failed refund {refund.refund_reference}")
            
            # Attempt automatic processing if configured
            if refund.is_automatic_refund:
                return self.process_automatic_refund(refund)
            else:
                return self.process_manual_refund(refund)
        
        except Exception as e:
            logger.exception(f"❌ Error retrying refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def cancel_refund(self, refund, cancellation_reason=None):
        """
        Cancel a refund request.
        
        Args:
            refund: OrderRefund instance
            cancellation_reason: Reason for cancellation
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status == OrderRefund.RefundStatus.PROCESSED:
            return False, "Cannot cancel a processed refund"
        
        if refund.status == OrderRefund.RefundStatus.CANCELLED:
            return False, "Refund already cancelled"
        
        try:
            refund.status = OrderRefund.RefundStatus.CANCELLED
            if cancellation_reason:
                if refund.processing_notes:
                    refund.processing_notes += f"\n\nCancellation: {cancellation_reason}"
                else:
                    refund.processing_notes = f"Cancellation: {cancellation_reason}"
            refund.save()
            
            logger.info(f"🚫 Refund {refund.refund_reference} cancelled: {cancellation_reason}")
            return True, "Refund cancelled successfully"
        
        except Exception as e:
            logger.exception(f"❌ Error cancelling refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def handle_stripe_refund_webhook(self, event):
        """
        Handle Stripe refund webhook events.
        
        Args:
            event: Stripe event object
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            refund_obj = event.data.object
            
            # Find refund by Stripe refund ID
            try:
                refund = OrderRefund.objects.get(stripe_refund_id=refund_obj['id'])
            except OrderRefund.DoesNotExist:
                # Try to find by metadata
                metadata = refund_obj.get('metadata', {})
                refund_id = metadata.get('refund_id')
                if refund_id:
                    try:
                        refund = OrderRefund.objects.get(id=refund_id)
                    except OrderRefund.DoesNotExist:
                        logger.warning(f"⚠️ Webhook received for unknown refund ID: {refund_id}")
                        return False, "Refund not found"
                else:
                    logger.warning(f"⚠️ Webhook received for unknown refund: {refund_obj['id']}")
                    return False, "Refund not found"
            
            # Update refund based on event type
            if event.type == 'charge.refund.updated':
                if refund_obj['status'] == 'succeeded':
                    # Only update Stripe status, don't auto-complete
                    # Admin must manually verify via complete_manual_refund
                    refund.stripe_refund_status = 'succeeded'
                    refund.save()
                    
                    logger.info(f"⏳ Webhook: Stripe refund {refund.refund_reference} succeeded. Awaiting admin verification.")
                    return True, "Stripe refund succeeded, awaiting verification"
                
                elif refund_obj['status'] == 'failed':
                    refund.status = OrderRefund.RefundStatus.FAILED
                    refund.stripe_failure_reason = refund_obj.get('failure_reason', 'Unknown')
                    refund.save()
                    logger.error(f"❌ Webhook: Refund {refund.refund_reference} failed: {refund.stripe_failure_reason}")
                    return False, "Refund failed"
            
            return True, "Webhook processed"
        
        except Exception as e:
            logger.exception(f"❌ Error processing refund webhook")
            return False, f"Error: {str(e)}"
    
    def _map_refund_reason_to_stripe(self, reason):
        """Map OrderRefund reason to Stripe refund reason"""
        mapping = {
            'CUSTOMER_REQUESTED': 'requested_by_customer',
            'DUPLICATE_ORDER': 'duplicate',
            'DAMAGED_ITEM': 'fraudulent',  # or 'requested_by_customer'
            'NOT_AS_DESCRIBED': 'requested_by_customer',
            'WRONG_SIZE': 'requested_by_customer',
            'CHANGED_MIND': 'requested_by_customer',
            'EVENT_CANCELLED': 'requested_by_customer',
            'ADMIN_DECISION': 'requested_by_customer',
            'OTHER': 'requested_by_customer'
        }
        return mapping.get(reason, 'requested_by_customer')


# Convenience function for quick access
def get_order_refund_service():
    """Get instance of OrderRefundService"""
    return OrderRefundService()
