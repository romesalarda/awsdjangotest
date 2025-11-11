"""
Stripe Refund Service
Handles automatic refund processing for Stripe payments with robust error handling.
"""
import stripe
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from apps.events.models import ParticipantRefund, EventPayment
from apps.shop.stripe_service import StripePaymentService

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
        if not refund.can_process_refund():
            return False, "Refund cannot be processed at this time"
        
        if refund.status != 'pending':
            return False, f"Refund is already {refund.status}"
        
        if not refund.is_automatic_refund:
            return False, "This refund is not configured for automatic processing"
        
        if not refund.stripe_payment_intent:
            return False, "No Stripe payment intent found for this refund"
        
        try:
            # Update status to processing
            refund.status = 'processing'
            refund.processed_at = timezone.now()
            refund.save()
            
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
                    'event_name': refund.event.event_name,
                    'refund_reference': refund.refund_reference
                }
            )
            
            # Update refund with Stripe information
            refund.stripe_refund_id = stripe_refund.id
            refund.stripe_refund_status = stripe_refund.status
            
            # Check if refund succeeded immediately
            if stripe_refund.status == 'succeeded':
                refund.status = 'completed'
                refund.completed_at = timezone.now()
            elif stripe_refund.status == 'failed':
                refund.status = 'failed'
                refund.stripe_failure_reason = stripe_refund.failure_reason
                refund.stripe_failure_message = "Stripe refund failed"
            
            refund.save()
            
            # Send notifications
            if refund.status == 'completed':
                self.send_refund_completed_notification(refund)
            else:
                self.send_refund_initiated_notification(refund)
            
            return True, f"Refund processed successfully. Stripe Refund ID: {stripe_refund.id}"
            
        except stripe.error.InvalidRequestError as e:
            # Invalid parameters were supplied to Stripe's API
            refund.status = 'failed'
            refund.stripe_failure_reason = 'invalid_request'
            refund.stripe_failure_message = str(e)
            refund.save()
            return False, f"Invalid refund request: {str(e)}"
            
        except stripe.error.CardError as e:
            # Card was declined or other card-related issue
            refund.status = 'failed'
            refund.stripe_failure_reason = e.code
            refund.stripe_failure_message = str(e)
            refund.save()
            return False, f"Card error: {str(e)}"
            
        except stripe.error.StripeError as e:
            # General Stripe error
            refund.status = 'failed'
            refund.stripe_failure_reason = 'stripe_error'
            refund.stripe_failure_message = str(e)
            refund.save()
            return False, f"Stripe error: {str(e)}"
            
        except Exception as e:
            # Unexpected error
            refund.status = 'failed'
            refund.stripe_failure_reason = 'unknown_error'
            refund.stripe_failure_message = str(e)
            refund.save()
            return False, f"Unexpected error: {str(e)}"
    
    def process_manual_refund(self, refund, processor_notes=None):
        """
        Mark manual refund as processing (bank transfer initiated).
        
        Args:
            refund: ParticipantRefund instance
            processor_notes: Optional notes from processor
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not refund.can_process_refund():
            return False, "Refund cannot be processed at this time"
        
        if refund.status != 'pending':
            return False, f"Refund is already {refund.status}"
        
        if refund.is_automatic_refund:
            return False, "This refund is configured for automatic processing"
        
        # Validate bank account details
        if not all([refund.bank_account_name, refund.bank_account_number, refund.bank_sort_code]):
            return False, "Bank account details are incomplete"
        
        try:
            refund.status = 'processing'
            refund.processed_at = timezone.now()
            
            if processor_notes:
                refund.processor_notes = processor_notes
            
            refund.save()
            
            # Send notification to participant
            self.send_manual_refund_initiated_notification(refund)
            
            return True, "Manual refund marked as processing"
            
        except Exception as e:
            return False, f"Error processing manual refund: {str(e)}"
    
    def complete_manual_refund(self, refund, processor_notes=None):
        """
        Mark manual refund as completed after bank transfer.
        
        Args:
            refund: ParticipantRefund instance
            processor_notes: Optional notes from processor
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status not in ['processing', 'pending']:
            return False, f"Cannot complete refund with status: {refund.status}"
        
        try:
            refund.status = 'completed'
            refund.completed_at = timezone.now()
            
            if processor_notes:
                refund.processor_notes = processor_notes
            
            refund.save()
            
            # Send completion notification
            self.send_refund_completed_notification(refund)
            
            return True, "Manual refund completed successfully"
            
        except Exception as e:
            return False, f"Error completing manual refund: {str(e)}"
    
    def retry_failed_refund(self, refund):
        """
        Retry a failed automatic refund.
        
        Args:
            refund: ParticipantRefund instance
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status != 'failed':
            return False, "Can only retry failed refunds"
        
        # Reset refund status
        refund.status = 'pending'
        refund.stripe_refund_id = None
        refund.stripe_refund_status = None
        refund.stripe_failure_reason = None
        refund.stripe_failure_message = None
        refund.save()
        
        # Process again
        return self.process_automatic_refund(refund)
    
    def cancel_refund(self, refund, cancellation_reason=None):
        """
        Cancel a pending refund.
        
        Args:
            refund: ParticipantRefund instance
            cancellation_reason: Reason for cancellation
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if refund.status not in ['pending', 'approved']:
            return False, f"Cannot cancel refund with status: {refund.status}"
        
        try:
            refund.status = 'cancelled'
            
            if cancellation_reason:
                refund.processor_notes = f"Cancelled: {cancellation_reason}"
            
            refund.save()
            
            # Send cancellation notification
            self.send_refund_cancelled_notification(refund)
            
            return True, "Refund cancelled successfully"
            
        except Exception as e:
            return False, f"Error cancelling refund: {str(e)}"
    
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
        """Map internal refund reason to Stripe reason"""
        reason_map = {
            'cancellation': 'requested_by_customer',
            'duplicate': 'duplicate',
            'event_cancelled': 'requested_by_customer',
            'overpayment': 'duplicate',
            'error': 'fraudulent',
            'other': 'requested_by_customer'
        }
        return reason_map.get(reason, 'requested_by_customer')
    
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
