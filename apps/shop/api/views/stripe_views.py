"""
Stripe Webhook Views
Handles incoming Stripe webhook events with security and idempotency.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import logging

from apps.shop.stripe_service import StripePaymentService

logger = logging.getLogger(__name__)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])  # Stripe webhooks don't use standard auth
def stripe_webhook(request):
    """
    Handle Stripe webhook events.
    
    Security:
    - Verifies webhook signature
    - Uses CSRF exempt (Stripe doesn't send CSRF token)
    - Validates event structure
    
    Supported events:
    - payment_intent.succeeded
    - payment_intent.payment_failed
    - charge.refunded
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    if not sig_header:
        logger.warning("Stripe webhook called without signature")
        return Response({'error': 'No signature'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Verify webhook signature
    event = StripePaymentService.verify_webhook_signature(payload, sig_header)
    
    if not event:
        logger.error("Invalid Stripe webhook signature")
        return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Log the event
    logger.info(f"Received Stripe webhook: {event['type']}")
    
    # Handle the event
    event_type = event['type']
    
    try:
        if event_type == 'payment_intent.succeeded':
            intent = event['data']['object']
            metadata = intent.get('metadata', {})
            payment_type = metadata.get('payment_type', 'product')  # Default to product for backward compatibility
            
            if payment_type == 'event_registration':
                # Handle event payment (registration + optional donation)
                StripePaymentService.handle_event_payment_succeeded(intent)
                return Response({'status': 'success', 'message': 'Event payment processed'}, status=status.HTTP_200_OK)
            else:
                # Handle product payment (existing flow)
                StripePaymentService.handle_payment_intent_succeeded(intent)
                return Response({'status': 'success', 'message': 'Product payment processed'}, status=status.HTTP_200_OK)
        
        elif event_type == 'payment_intent.payment_failed':
            intent = event['data']['object']
            metadata = intent.get('metadata', {})
            payment_type = metadata.get('payment_type', 'product')
            
            if payment_type == 'event_registration':
                # Handle event payment failure
                StripePaymentService.handle_event_payment_failed(intent)
                return Response({'status': 'success', 'message': 'Event payment failure recorded'}, status=status.HTTP_200_OK)
            else:
                # Handle product payment failure
                StripePaymentService.handle_payment_intent_failed(intent)
                return Response({'status': 'success', 'message': 'Product payment failure recorded'}, status=status.HTTP_200_OK)
        
        elif event_type == 'charge.refunded':
            # Handle refunds
            charge = event['data']['object']
            logger.info(f"Refund processed for charge {charge['id']}")
            # Additional refund handling can be added here
            return Response({'status': 'success', 'message': 'Refund recorded'}, status=status.HTTP_200_OK)
        
        else:
            # Unhandled event type
            logger.info(f"Unhandled Stripe event type: {event_type}")
            return Response({'status': 'success', 'message': 'Event received but not handled'}, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}", exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_payment_intent(request, cart_id):
    """
    Create a Stripe PaymentIntent for a cart.
    Called from frontend when user selects Stripe as payment method.
    
    Requires authentication.
    """
    from apps.shop.models.shop_models import EventCart
    from apps.shop.models.payments import ProductPayment, ProductPaymentMethod
    from django.shortcuts import get_object_or_404
    
    cart = get_object_or_404(EventCart, uuid=cart_id)
    
    # Security check
    if cart.user != request.user and not request.user.is_superuser:
        return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
    
    # Get Stripe payment method
    stripe_method = ProductPaymentMethod.objects.filter(
        method=ProductPaymentMethod.MethodType.STRIPE,
        is_active=True
    ).first()
    
    if not stripe_method:
        return Response({'error': 'Stripe payment method not configured'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if payment already exists for this cart
    existing_payment = ProductPayment.objects.filter(
        cart=cart,
        method=stripe_method,
        status=ProductPayment.PaymentStatus.PENDING
    ).first()
    
    if existing_payment and existing_payment.stripe_payment_intent:
        # Return existing intent
        return Response({
            'client_secret': existing_payment.stripe_payment_intent,
            'payment_id': existing_payment.id
        }, status=status.HTTP_200_OK)
    
    # Create payment record (this should ideally be done in checkout endpoint)
    # For now, this is a simplified version
    return Response({
        'error': 'Please use the checkout endpoint first'
    }, status=status.HTTP_400_BAD_REQUEST)
