"""
Participant Refund Service
Handles automatic and manual refund processing for event registration payments with robust error handling.
"""
import stripe
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from apps.events.models import ParticipantRefund, EventPayment
from apps.shop.stripe_service import StripePaymentService

logger = logging.getLogger(__name__)

# Initialize Stripe

STRIPE_TEST_MODE = getattr(settings, 'STRIPE_TEST_MODE', True)
STRIPE_SECRET_KEY = getattr(settings, 'STRIPE_SECRET_KEY_TEST' if STRIPE_TEST_MODE else 'STRIPE_SECRET_KEY_LIVE', None)
STRIPE_WEBHOOK_SECRET = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class RefundService:
    """Service for processing refunds through Stripe and managing refund workflow"""
    
    def __init__(self):
        self.stripe_service = StripePaymentService()
    
    def process_automatic_refund(self, refund):
        """
        Process automatic refund through Stripe.
        
        Args:
            refund: ParticipantRefund instance
            
        Returns:
            tuple: (success: bool, message: str)
        """
        # Validation checks
        can_process, message = refund.can_process_refund()
        if not can_process:
            logger.warning(f"Refund {refund.refund_reference} cannot be processed: {message}")
            return False, message
        
        if refund.status not in [ParticipantRefund.RefundStatus.PENDING]:
            logger.warning(f"Refund {refund.refund_reference} has invalid status: {refund.status}")
            return False, f"Refund status must be PENDING. Current status: {refund.get_status_display()}"
        
        if not refund.is_automatic_refund:
            logger.warning(f"Refund {refund.refund_reference} is not configured for automatic processing")
            return False, "This refund is not configured for automatic processing"
        
        if not refund.stripe_payment_intent:
            logger.error(f"Refund {refund.refund_reference} missing Stripe payment intent")
            return False, "No Stripe payment intent found for this refund"
        
        if not refund.event_payment or refund.event_payment.status != EventPayment.PaymentStatus.REFUND_PROCESSING:
            return False, "Event payment must be in REFUND_PROCESSING status"
        
        try:
            # Update status to processing
            refund.status = ParticipantRefund.RefundStatus.IN_PROGRESS
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
                    'participant_id': str(refund.participant.id),
                    'event_id': str(refund.event.id),
                    'event_code': refund.event.event_code,
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
            refund.status = ParticipantRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.error(f"❌ Stripe invalid request for refund {refund.refund_reference}: {e}")
            return False, f"Stripe error: {str(e)}"
        
        except stripe.error.CardError as e:
            refund.status = ParticipantRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.error(f"❌ Stripe card error for refund {refund.refund_reference}: {e}")
            return False, f"Card error: {str(e)}"
        
        except Exception as e:
            refund.status = ParticipantRefund.RefundStatus.FAILED
            refund.stripe_failure_reason = str(e)
            refund.save()
            logger.exception(f"❌ Unexpected error processing refund {refund.refund_reference}")
            return False, f"Unexpected error: {str(e)}"
    
    def process_manual_refund(self, refund, processor_notes=None):
        """
        Initiate manual refund processing (bank transfer, cash, etc.).
        Marks refund as in-progress and awaits manual completion.
        
        Args:
            refund: ParticipantRefund instance
            processor_notes: Optional notes about processing
            
        Returns:
            tuple: (success: bool, message: str)
        """
        can_process, message = refund.can_process_refund()
        if not can_process:
            logger.warning(f"Manual refund {refund.refund_reference} cannot be processed: {message}")
            return False, message
        
        if refund.status not in [ParticipantRefund.RefundStatus.PENDING]:
            logger.warning(f"Manual refund {refund.refund_reference} has invalid status: {refund.status}")
            return False, f"Refund status must be PENDING. Current status: {refund.get_status_display()}"
        
        if not refund.event_payment or refund.event_payment.status != EventPayment.PaymentStatus.REFUND_PROCESSING:
            return False, "Event payment must be in REFUND_PROCESSING status"
        
        try:
            refund.status = ParticipantRefund.RefundStatus.IN_PROGRESS
            if processor_notes:
                refund.processing_notes = processor_notes
            refund.save()
            
            logger.info(f"⏳ Manual refund {refund.refund_reference} marked as in-progress")
            return True, "Manual refund initiated. Payment should be sent outside the system. Please verify completion to finalize."
        
        except Exception as e:
            logger.exception(f"❌ Error initiating manual refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def complete_manual_refund(self, refund, processor_notes=None):
        """
        Mark manual refund as completed.
        
        Args:
            refund: ParticipantRefund instance
            processor_notes: Optional completion notes
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status == ParticipantRefund.RefundStatus.PROCESSED:
            return False, "Refund already processed"
        
        if refund.status != ParticipantRefund.RefundStatus.IN_PROGRESS:
            return False, "Refund must be in IN_PROGRESS status before completing"
        
        try:
            refund.status = ParticipantRefund.RefundStatus.PROCESSED
            refund.processed_at = timezone.now()
            if processor_notes:
                if refund.processing_notes:
                    refund.processing_notes += f"\n\n{processor_notes}"
                else:
                    refund.processing_notes = processor_notes
            refund.save()
            
            # Update event payment status
            if refund.event_payment:
                refund.event_payment.status = EventPayment.PaymentStatus.REFUNDED
                refund.event_payment.save()
                logger.info(f"Event payment {refund.event_payment.event_payment_tracking_number} marked as REFUNDED")
            
            logger.info(f"✅ Manual refund {refund.refund_reference} completed")
            return True, "Manual refund marked as completed"
        
        except Exception as e:
            logger.exception(f"❌ Error completing manual refund {refund.refund_reference}")
            return False, f"Error: {str(e)}"
    
    def retry_failed_refund(self, refund):
        """
        Retry a failed refund.
        
        Args:
            refund: ParticipantRefund instance
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status != ParticipantRefund.RefundStatus.FAILED:
            return False, "Only failed refunds can be retried"
        
        try:
            # Reset refund status
            refund.status = ParticipantRefund.RefundStatus.PENDING
            refund.stripe_refund_id = None
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
            refund: ParticipantRefund instance
            cancellation_reason: Reason for cancellation
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status == ParticipantRefund.RefundStatus.PROCESSED:
            return False, "Cannot cancel a processed refund"
        
        if refund.status == ParticipantRefund.RefundStatus.CANCELLED:
            return False, "Refund already cancelled"
        
        try:
            refund.status = ParticipantRefund.RefundStatus.CANCELLED
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
            event: Stripe webhook event
            
        Returns:
            bool: Success status
        """
        try:
            refund_obj = event['data']['object']
            refund_id = refund_obj.get('metadata', {}).get('refund_id')
            
            if not refund_id:
                # Try to find by Stripe refund ID
                try:
                    refund = ParticipantRefund.objects.get(stripe_refund_id=refund_obj['id'])
                except ParticipantRefund.DoesNotExist:
                    return False
            else:
                try:
                    refund = ParticipantRefund.objects.get(id=refund_id)
                except ParticipantRefund.DoesNotExist:
                    return False
            
            # Update refund based on event type
            if event['type'] == 'charge.refund.updated':
                refund.stripe_refund_status = refund_obj['status']
                
                if refund_obj['status'] == 'succeeded':
                    refund.status = 'completed'
                    refund.completed_at = timezone.now()
                    self.send_refund_completed_notification(refund)
                    
                elif refund_obj['status'] == 'failed':
                    refund.status = 'failed'
                    refund.stripe_failure_reason = refund_obj.get('failure_reason')
                    refund.stripe_failure_message = refund_obj.get('failure_message')
                    self.send_refund_failed_notification(refund)
                
                refund.save()
            
            return True
            
        except Exception as e:
            print(f"Error handling refund webhook: {str(e)}")
            return False
    
    def _map_refund_reason_to_stripe(self, reason):
        """Map ParticipantRefund reason to Stripe refund reason"""
        mapping = {
            'USER_REQUESTED': 'requested_by_customer',
            'EVENT_CANCELLED': 'requested_by_customer',
            'ADMIN_DECISION': 'requested_by_customer',
            'DUPLICATE_PAYMENT': 'duplicate',
            'PARTICIPANT_REMOVED': 'requested_by_customer',
            'OTHER': 'requested_by_customer'
        }
        return mapping.get(reason, 'requested_by_customer')
    
    # Notification methods
    
    def send_refund_created_notification(self, refund):
        """Send notification when refund is created"""
        try:
            # Notify participant
            if refund.participant.user and refund.participant.user.email:
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Refund Request Created - {refund.event.event_name}",
                    template='emails/refund_created_participant.html',
                    context={'refund': refund}
                )
                refund.participant_notified = True
            
            # Notify secretariat/contact
            if refund.refund_contact_email:
                self._send_email(
                    to_email=refund.refund_contact_email,
                    subject=f"New Refund Request - {refund.event.event_name}",
                    template='emails/refund_created_secretariat.html',
                    context={'refund': refund}
                )
                refund.secretariat_notified = True
            
            refund.save()
            
        except Exception as e:
            print(f"Error sending refund created notification: {str(e)}")
    
    def send_refund_initiated_notification(self, refund):
        """Send notification when refund processing is initiated"""
        try:
            if refund.participant.user and refund.participant.user.email:
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Refund Processing - {refund.event.event_name}",
                    template='emails/refund_processing.html',
                    context={'refund': refund}
                )
                refund.participant_notified = True
                refund.save()
                
        except Exception as e:
            print(f"Error sending refund initiated notification: {str(e)}")
    
    def send_manual_refund_initiated_notification(self, refund):
        """Send notification when manual refund is initiated"""
        try:
            if refund.participant.user and refund.participant.user.email:
                estimated_days = refund.refund_processing_time or "5-7 business days"
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Bank Transfer Refund Initiated - {refund.event.event_name}",
                    template='emails/manual_refund_initiated.html',
                    context={
                        'refund': refund,
                        'estimated_processing_time': estimated_days
                    }
                )
                refund.participant_notified = True
                refund.save()
                
        except Exception as e:
            print(f"Error sending manual refund initiated notification: {str(e)}")
    
    def send_refund_completed_notification(self, refund):
        """Send notification when refund is completed"""
        try:
            if refund.participant.user and refund.participant.user.email:
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Refund Completed - {refund.event.event_name}",
                    template='emails/refund_completed.html',
                    context={'refund': refund}
                )
                refund.participant_notified = True
                refund.save()
                
        except Exception as e:
            print(f"Error sending refund completed notification: {str(e)}")
    
    def send_refund_failed_notification(self, refund):
        """Send notification when refund fails"""
        try:
            # Notify participant
            if refund.participant.user and refund.participant.user.email:
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Refund Failed - {refund.event.event_name}",
                    template='emails/refund_failed.html',
                    context={'refund': refund}
                )
            
            # Notify secretariat
            if refund.refund_contact_email:
                self._send_email(
                    to_email=refund.refund_contact_email,
                    subject=f"Refund Failed - Action Required",
                    template='emails/refund_failed_secretariat.html',
                    context={'refund': refund}
                )
                
        except Exception as e:
            print(f"Error sending refund failed notification: {str(e)}")
    
    def send_refund_cancelled_notification(self, refund):
        """Send notification when refund is cancelled"""
        try:
            if refund.participant.user and refund.participant.user.email:
                self._send_email(
                    to_email=refund.participant.user.email,
                    subject=f"Refund Cancelled - {refund.event.event_name}",
                    template='emails/refund_cancelled.html',
                    context={'refund': refund}
                )
                
        except Exception as e:
            print(f"Error sending refund cancelled notification: {str(e)}")
    
    def _send_email(self, to_email, subject, template, context):
        """Helper method to send email"""
        try:
            html_message = render_to_string(template, context)
            send_mail(
                subject=subject,
                message='',  # Plain text version
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                html_message=html_message,
                fail_silently=False
            )
        except Exception as e:
            print(f"Error sending email to {to_email}: {str(e)}")
            raise


# Convenience function for quick access
def get_refund_service():
    """Get instance of RefundService"""
    return RefundService()
