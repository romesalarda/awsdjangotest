"""
Stripe Integration Service
Production-ready Stripe payment handling with security best practices.

Setup Instructions:
1. Install stripe: pip install stripe
2. Set environment variables:
   - STRIPE_SECRET_KEY_TEST (for test mode)
   - STRIPE_SECRET_KEY_LIVE (for production)
   - STRIPE_WEBHOOK_SECRET (for webhook signature verification)
3. Configure webhooks in Stripe Dashboard pointing to: /api/shop/stripe/webhook/
"""

import stripe
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import logging

from apps.shop.models.payments import ProductPayment, ProductPaymentLog, ProductPaymentMethod
from apps.shop.models.shop_models import EventCart, ProductPurchaseTracker
from apps.events.models import EventPayment, DonationPayment

logger = logging.getLogger(__name__)

# Initialize Stripe with test key (configure in settings)
STRIPE_TEST_MODE = getattr(settings, 'STRIPE_TEST_MODE', True)
STRIPE_SECRET_KEY = getattr(settings, 'STRIPE_SECRET_KEY_TEST' if STRIPE_TEST_MODE else 'STRIPE_SECRET_KEY_LIVE', None)
STRIPE_WEBHOOK_SECRET = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class StripePaymentService:
    """
    Handles all Stripe payment operations with production-grade security.
    """
    
    @staticmethod
    def create_payment_intent(payment: ProductPayment, metadata: dict = None):
        """
        Create a Stripe PaymentIntent for the given payment.
        
        Args:
            payment: ProductPayment instance
            metadata: Optional additional metadata to attach
            
        Returns:
            PaymentIntent object or None if error
        """
        if not STRIPE_SECRET_KEY:
            logger.error("Stripe API key not configured")
            return None
        
        try:
            # Convert amount to cents (Stripe uses smallest currency unit)
            amount_cents = int(payment.amount * 100)
            
            # Prepare metadata
            intent_metadata = {
                'payment_id': str(payment.id),
                'payment_reference': payment.payment_reference_id,
                'cart_id': str(payment.cart.uuid) if payment.cart else None,
                'user_id': str(payment.user.id) if payment.user else None,
                'event_id': str(payment.cart.event.id) if payment.cart and payment.cart.event else None,
            }
            
            if metadata:
                intent_metadata.update(metadata)
            
            # Create PaymentIntent with idempotency key
            idempotency_key = f"payment_{payment.id}_{timezone.now().timestamp()}"
            
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=payment.currency.lower(),
                payment_method_types=['card'],
                description=f"Order {payment.cart.order_reference_id if payment.cart else 'N/A'}",
                metadata=intent_metadata,
                receipt_email=payment.email,
                idempotency_key=idempotency_key,
                # Automatic payment methods for future expansion
                # automatic_payment_methods={'enabled': True, 'allow_redirects': 'never'}
            )
            
            # Store Stripe payment intent ID
            payment.stripe_payment_intent = intent.id
            payment.save()
            
            # Log the creation
            ProductPaymentLog.log_action(
                payment=payment,
                action='stripe_intent_created',
                notes=f"Stripe PaymentIntent created: {intent.id}",
                metadata={'intent_id': intent.id, 'amount_cents': amount_cents}
            )
            
            logger.info(f"Created Stripe PaymentIntent {intent.id} for payment {payment.payment_reference_id}")
            return intent
            
        except Exception as e:
            logger.error(f"Stripe error creating PaymentIntent: {e}")
            ProductPaymentLog.log_action(
                payment=payment,
                action='stripe_error',
                notes=f"Failed to create PaymentIntent: {str(e)}"
            )
            return None
    
    @staticmethod
    def handle_payment_intent_succeeded(intent):
        """
        Handle successful payment intent from webhook.
        Updates payment status and records purchase tracking.
        """
        try:
            payment_id = intent.metadata.get('payment_id')
            if not payment_id:
                logger.error(f"No payment_id in intent metadata: {intent.id}")
                return False
            
            payment = ProductPayment.objects.get(id=payment_id)
            
            # Update payment status
            old_status = payment.status
            payment.status = ProductPayment.PaymentStatus.SUCCEEDED
            payment.approved = True
            payment.paid_at = timezone.now()
            payment.save()
            
            # Update cart status
            if payment.cart:
                payment.cart.cart_status = EventCart.CartStatus.COMPLETED
                payment.cart.approved = True
                payment.cart.save()
                
                # Record purchase tracking for max purchase enforcement
                for order in payment.cart.orders.all():
                    ProductPurchaseTracker.record_purchase(
                        user=payment.user,
                        product=order.product,
                        quantity=order.quantity
                    )
                    
                    # Deduct stock
                    product = order.product
                    product.stock = max(0, product.stock - order.quantity)
                    product.save()
            
            # Log success
            ProductPaymentLog.log_action(
                payment=payment,
                action='payment_succeeded',
                old_status=old_status,
                new_status=ProductPayment.PaymentStatus.SUCCEEDED,
                notes=f"Stripe payment succeeded: {intent.id}",
                metadata={'intent_id': intent.id, 'amount_received': intent.amount_received}
            )
            
            logger.info(f"Payment {payment.payment_reference_id} succeeded via Stripe")
            return True
            
        except ProductPayment.DoesNotExist:
            logger.error(f"Payment not found for intent {intent.id}")
            return False
        except Exception as e:
            logger.error(f"Error handling payment success: {e}")
            return False
    
    @staticmethod
    def handle_payment_intent_failed(intent):
        """
        Handle failed payment intent from webhook.
        Unlocks cart and logs failure.
        """
        try:
            payment_id = intent.metadata.get('payment_id')
            if not payment_id:
                logger.error(f"No payment_id in intent metadata: {intent.id}")
                return False
            
            payment = ProductPayment.objects.get(id=payment_id)
            
            # Update payment status
            old_status = payment.status
            payment.status = ProductPayment.PaymentStatus.FAILED
            payment.save()
            
            # Unlock cart so user can try again
            if payment.cart:
                payment.cart.cart_status = EventCart.CartStatus.ACTIVE
                payment.cart.locked_at = None
                payment.cart.lock_expires_at = None
                payment.cart.submitted = False
                payment.cart.save()
            
            # Log failure
            failure_reason = intent.last_payment_error.message if intent.last_payment_error else "Unknown"
            ProductPaymentLog.log_action(
                payment=payment,
                action='payment_failed',
                old_status=old_status,
                new_status=ProductPayment.PaymentStatus.FAILED,
                notes=f"Stripe payment failed: {failure_reason}",
                metadata={'intent_id': intent.id, 'failure_reason': failure_reason}
            )
            
            logger.warning(f"Payment {payment.payment_reference_id} failed: {failure_reason}")
            return True
            
        except ProductPayment.DoesNotExist:
            logger.error(f"Payment not found for intent {intent.id}")
            return False
        except Exception as e:
            logger.error(f"Error handling payment failure: {e}")
            return False
    
    @staticmethod
    def verify_webhook_signature(payload, signature):
        """
        Verify Stripe webhook signature for security.
        
        Args:
            payload: Raw request body
            signature: Stripe-Signature header value
            
        Returns:
            Event object if valid, None otherwise
        """
        if not STRIPE_WEBHOOK_SECRET:
            logger.error("Stripe webhook secret not configured")
            return None
        
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError:
            logger.error("Invalid webhook payload")
            return None
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid webhook signature")
            return None
    
    @staticmethod
    def create_refund(payment: ProductPayment, amount: Decimal = None, reason: str = None):
        """
        Create a refund for a payment.
        
        Args:
            payment: ProductPayment instance
            amount: Amount to refund (None for full refund)
            reason: Reason for refund
            
        Returns:
            Refund object or None if error
        """
        if not payment.stripe_payment_intent:
            logger.error(f"No Stripe PaymentIntent for payment {payment.payment_reference_id}")
            return None
        
        try:
            refund_data = {
                'payment_intent': payment.stripe_payment_intent,
                'reason': reason or 'requested_by_customer',
            }
            
            if amount:
                refund_data['amount'] = int(amount * 100)  # Convert to cents
            
            refund = stripe.Refund.create(**refund_data)
            
            # Log refund
            ProductPaymentLog.log_action(
                payment=payment,
                action='refund_created',
                notes=f"Stripe refund created: {refund.id}. Reason: {reason}",
                metadata={'refund_id': refund.id, 'amount': amount or payment.amount}
            )
            
            logger.info(f"Created refund {refund.id} for payment {payment.payment_reference_id}")
            return refund
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating refund: {e}")
            return None
    
    # ==================== EVENT PAYMENT METHODS ====================
    
    @staticmethod
    def create_event_payment_intent(event_payment: 'EventPayment', donation_payment: 'DonationPayment' = None, metadata: dict = None):
        """
        Create a Stripe PaymentIntent for event registration payment, optionally combined with donation.
        
        Args:
            event_payment: EventPayment instance (required)
            donation_payment: Optional DonationPayment instance to combine in one transaction
            metadata: Optional additional metadata to attach
            
        Returns:
            PaymentIntent object or None if error
        """
        if not STRIPE_SECRET_KEY:
            logger.error("Stripe API key not configured")
            return None
        
        try:
            # Calculate total amount (event + optional donation)
            total_amount = event_payment.amount
            if donation_payment:
                total_amount += Decimal(donation_payment.amount)
            
            # Convert amount to cents (Stripe uses smallest currency unit)
            amount_cents = int(total_amount * 100)
            
            # Prepare metadata
            intent_metadata = {
                'payment_type': 'event_registration',
                'event_payment_id': str(event_payment.id),
                'event_payment_tracking': event_payment.event_payment_tracking_number,
                'participant_id': str(event_payment.user.id) if event_payment.user else None,
                'event_id': str(event_payment.event.id) if event_payment.event else None,
                'event_name': event_payment.event.name if event_payment.event else None,
                'package_id': str(event_payment.package.id) if event_payment.package else None,
                'package_name': event_payment.package.name if event_payment.package else None,
                'has_donation': 'true' if donation_payment else 'false',
            }
            
            if donation_payment:
                intent_metadata.update({
                    'donation_payment_id': str(donation_payment.id),
                    'donation_tracking': donation_payment.event_payment_tracking_number,
                    'donation_amount': str(donation_payment.amount),
                })
            
            if metadata:
                intent_metadata.update(metadata)
            
            # Get participant email for receipt
            participant_email = None
            if event_payment.user and event_payment.user.user:
                participant_email = event_payment.user.user.primary_email
            
            # Create PaymentIntent with idempotency key
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=event_payment.currency.lower(),
                metadata=intent_metadata,
                description=f"Event Registration: {event_payment.event.name if event_payment.event else 'Event'}",
                receipt_email=participant_email,
                idempotency_key=f"event_payment_{event_payment.id}_{int(timezone.now().timestamp())}",
            )
            
            # Store payment intent ID
            event_payment.stripe_payment_intent = payment_intent.id
            event_payment.save()
            
            if donation_payment:
                donation_payment.stripe_payment_intent = payment_intent.id
                donation_payment.save()
            
            logger.info(f"Created Stripe PaymentIntent {payment_intent.id} for event payment {event_payment.event_payment_tracking_number}")
            
            return payment_intent
            
        except Exception as e:
            logger.error(f"Error creating Stripe PaymentIntent for event payment: {e}")
            return None
    
    @staticmethod
    def handle_event_payment_succeeded(intent):
        """
        Handle successful event payment intent from webhook.
        Updates payment status for both EventPayment and optional DonationPayment.
        """
        try:
            metadata = intent.get('metadata', {})
            event_payment_id = metadata.get('event_payment_id')
            donation_payment_id = metadata.get('donation_payment_id')
            
            if not event_payment_id:
                logger.error(f"No event_payment_id in PaymentIntent {intent.get('id')} metadata")
                return
            
            # Update EventPayment
            try:
                event_payment = EventPayment.objects.get(id=event_payment_id)
                event_payment.status = EventPayment.PaymentStatus.SUCCEEDED
                event_payment.paid_at = timezone.now()
                event_payment.verified = True
                event_payment.save()
                
                logger.info(f"Event payment {event_payment.event_payment_tracking_number} marked as succeeded")
                
                # Update participant status to CONFIRMED if needed
                if event_payment.user:
                    from apps.events.models import EventParticipant
                    if event_payment.user.status == EventParticipant.Status.PENDING:
                        event_payment.user.status = EventParticipant.Status.CONFIRMED
                        event_payment.user.save()
                        logger.info(f"Participant {event_payment.user.event_pax_id} status updated to CONFIRMED")
                
            except EventPayment.DoesNotExist:
                logger.error(f"EventPayment {event_payment_id} not found")
            
            # Update DonationPayment if exists
            if donation_payment_id:
                try:
                    donation_payment = DonationPayment.objects.get(id=donation_payment_id)
                    donation_payment.status = DonationPayment.PaymentStatus.SUCCEEDED
                    donation_payment.paid_at = timezone.now()
                    donation_payment.verified = True
                    donation_payment.save()
                    
                    logger.info(f"Donation payment {donation_payment.event_payment_tracking_number} marked as succeeded")
                    
                except DonationPayment.DoesNotExist:
                    logger.error(f"DonationPayment {donation_payment_id} not found")
            
        except Exception as e:
            logger.error(f"Error handling event payment success: {e}")
    
    @staticmethod
    def handle_event_payment_failed(intent):
        """
        Handle failed event payment intent from webhook.
        Updates payment status and logs failure.
        """
        try:
            metadata = intent.get('metadata', {})
            event_payment_id = metadata.get('event_payment_id')
            donation_payment_id = metadata.get('donation_payment_id')
            
            if not event_payment_id:
                logger.error(f"No event_payment_id in failed PaymentIntent {intent.get('id')} metadata")
                return
            
            # Get failure reason
            failure_message = "Payment failed"
            if 'last_payment_error' in intent and intent['last_payment_error']:
                failure_message = intent['last_payment_error'].get('message', failure_message)
            
            # Update EventPayment
            try:
                event_payment = EventPayment.objects.get(id=event_payment_id)
                event_payment.status = EventPayment.PaymentStatus.FAILED
                event_payment.save()
                
                logger.warning(f"Event payment {event_payment.event_payment_tracking_number} marked as failed: {failure_message}")
                
            except EventPayment.DoesNotExist:
                logger.error(f"EventPayment {event_payment_id} not found")
            
            # Update DonationPayment if exists
            if donation_payment_id:
                try:
                    donation_payment = DonationPayment.objects.get(id=donation_payment_id)
                    donation_payment.status = DonationPayment.PaymentStatus.FAILED
                    donation_payment.save()
                    
                    logger.warning(f"Donation payment {donation_payment.event_payment_tracking_number} marked as failed")
                    
                except DonationPayment.DoesNotExist:
                    logger.error(f"DonationPayment {donation_payment_id} not found")
            
        except Exception as e:
            logger.error(f"Error handling event payment failure: {e}")
    
    @staticmethod
    def create_event_refund(event_payment: 'EventPayment', amount: Decimal = None, reason: str = None):
        """
        Create a refund for an event payment.
        
        Args:
            event_payment: EventPayment instance
            amount: Amount to refund (None for full refund)
            reason: Reason for refund
            
        Returns:
            Refund object or None if error
        """
        if not event_payment.stripe_payment_intent:
            logger.error(f"No Stripe PaymentIntent for event payment {event_payment.event_payment_tracking_number}")
            return None
        
        try:
            refund_data = {
                'payment_intent': event_payment.stripe_payment_intent,
                'reason': reason or 'requested_by_customer',
            }
            
            if amount:
                refund_data['amount'] = int(amount * 100)  # Convert to cents
            
            refund = stripe.Refund.create(**refund_data)
            
            logger.info(f"Created refund {refund.id} for event payment {event_payment.event_payment_tracking_number}")
            return refund
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating event refund: {e}")
            return None
