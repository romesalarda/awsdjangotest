"""
ViewSet for managing order refunds.
Provides comprehensive refund tracking, filtering, and processing capabilities.
"""
from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.db.models import Q, Sum, Count, Avg
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import threading
import logging

from apps.shop.models import OrderRefund, EventCart, ProductPayment
from apps.shop.api.serializers import (
    OrderRefundListSerializer,
    OrderRefundDetailSerializer,
    CreateOrderRefundSerializer,
    ProcessOrderRefundSerializer,
)
from apps.shop.services.order_refund_service import get_order_refund_service
from core.event_permissions import has_event_permission

logger = logging.getLogger(__name__)


class OrderRefundViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing order refunds.
    
    Provides comprehensive refund tracking with advanced filtering:
    - Filter by event, cart, status, date ranges
    - Search by customer name, email, refund reference, cart reference
    - Sort by amount, date, status
    - Batch operations for processing multiple refunds
    
    list: Get all refunds with lightweight data
    retrieve: Get detailed refund information
    create: Create a new refund record
    update: Update refund details (admin only)
    partial_update: Partially update refund
    destroy: Delete refund record (admin only, use cancel instead)
    
    Custom actions:
    - initiate_refund: Create and optionally auto-process refund
    - process_refund: Mark refund as processed (manual or confirm automatic)
    - cancel_refund: Cancel a refund request
    - retry_refund: Retry a failed refund
    - pending_refunds: Get all pending refunds
    - refund_statistics: Get refund statistics for events
    """
    
    queryset = OrderRefund.objects.select_related(
        'cart',
        'cart__event',
        'payment',
        'user',
        'event',
        'initiated_by',
        'processed_by'
    ).all()
    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filtering options
    filterset_fields = {
        'status': ['exact', 'in'],
        'event': ['exact'],
        'cart': ['exact'],
        'user': ['exact'],
        'created_at': ['gte', 'lte', 'exact'],
        'processed_at': ['gte', 'lte', 'isnull'],
        'refund_amount': ['gte', 'lte', 'exact'],
        'is_automatic_refund': ['exact'],
        'stock_restored': ['exact'],
    }
    
    # Search functionality
    search_fields = [
        'refund_reference',
        'customer_name',
        'customer_email',
        'cart__order_reference_id',
        'event__name',
        'event__event_code',
        'reason_details'
    ]
    
    # Sorting options
    ordering_fields = [
        'created_at',
        'processed_at',
        'refund_amount',
        'status',
        'event__start_date'
    ]
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return OrderRefundListSerializer
        elif self.action in ['process_refund', 'initiate_refund']:
            return ProcessOrderRefundSerializer
        elif self.action == 'create':
            return CreateOrderRefundSerializer
        return OrderRefundDetailSerializer
    
    def get_queryset(self):
        """Filter queryset based on permissions and query params"""
        queryset = super().get_queryset()
        user = self.request.user
        
        # Filter by event if provided
        event_id = self.request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event__id=event_id)
        
        # Filter by cart if provided
        cart_id = self.request.query_params.get('cart_id')
        if cart_id:
            queryset = queryset.filter(cart__uuid=cart_id)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status_filter')
        if status_filter:
            if status_filter == 'pending':
                queryset = queryset.filter(
                    status__in=[
                        OrderRefund.RefundStatus.PENDING,
                        OrderRefund.RefundStatus.IN_PROGRESS
                    ]
                )
            elif status_filter == 'processed':
                queryset = queryset.filter(status=OrderRefund.RefundStatus.PROCESSED)
            elif status_filter == 'failed':
                queryset = queryset.filter(status=OrderRefund.RefundStatus.FAILED)
        
        # Non-staff users can only see their own refunds
        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(user=user)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set initiated_by to current user"""
        serializer.save(initiated_by=self.request.user)
    
    @action(detail=False, methods=['post'], url_name='initiate-refund', url_path='initiate')
    def initiate_refund(self, request):
        """
        Create a new refund and optionally process it automatically.
        
        Request body:
        {
            "cart_id": "uuid",
            "refund_reason": "CUSTOMER_REQUESTED",
            "reason_details": "Customer changed mind",
            "auto_process": true  // Optional: attempt automatic processing
        }
        """
        print(request.data  )
        cart_id = request.data.get('cart_id')
        if not cart_id:
            return Response(
                {'error': 'cart_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            cart = EventCart.objects.select_related('event', 'user').get(uuid=cart_id)
        except EventCart.DoesNotExist:
            return Response(
                {'error': 'Cart not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Permission check - must have canApproveMerchPayments
        if cart.event:
            if not has_event_permission(request.user, cart.event, 'can_approve_merch_payments'):
                return Response(
                    {'error': 'You do not have permission to process refunds for this event'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get payment for this cart
        payment = ProductPayment.objects.filter(cart=cart).first()
        
        # Validate payment exists and is paid
        if not payment:
            return Response(
                {'error': 'Cannot refund unpaid order. No payment record found.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if payment.status not in [ProductPayment.PaymentStatus.PENDING, ProductPayment.PaymentStatus.SUCCEEDED]:
            return Response(
                {'error': f'Cannot refund unpaid order. Payment status is: {payment.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine if automatic refund is possible
        is_automatic = False
        stripe_payment_intent = None
        if payment and payment.stripe_payment_intent and payment.method:
            is_automatic = payment.method.supports_automatic_refunds
            stripe_payment_intent = payment.stripe_payment_intent
        
        # Prepare refund data
        refund_data = {
            'cart': cart.uuid,
            'payment': payment.id if payment else None,
            'user': cart.user.id if cart.user else None,
            'event': cart.event.id if cart.event else None,
            'refund_amount': cart.total,
            'refund_reason': request.data.get('refund_reason', 'CUSTOMER_REQUESTED'),
            'reason_details': request.data.get('reason_details', ''),
            'is_automatic_refund': is_automatic,
            'stripe_payment_intent': stripe_payment_intent,
            'original_payment_method': payment.method.get_method_display() if payment and payment.method else None,
        }
        
        serializer = CreateOrderRefundSerializer(data=refund_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        refund = serializer.save(initiated_by=request.user)
        
        # Update cart status to PENDING_REFUND
        cart.cart_status = EventCart.CartStatus.PENDING_REFUND
        cart.save()
        
        # Update order items status to PENDING_REFUND
        from apps.shop.models import EventProductOrder
        order_items = EventProductOrder.objects.filter(cart=cart)
        order_items.update(
            status=EventProductOrder.Status.PENDING_REFUND,
            refund_status='PENDING'
        )
        
        logger.info(f"✨ Refund {refund.refund_reference} created by {request.user.primary_email}")
        logger.info(f"Cart {cart.order_reference_id} and {order_items.count()} items marked as pending refund")
        
        # Send notification email (in background)
        def send_email():
            try:
                from apps.shop.email_utils import send_order_refund_created_email
                send_order_refund_created_email(refund)
                logger.info(f"📧 Refund created email sent for {refund.refund_reference}")
            except Exception as e:
                logger.error(f"⚠️ Failed to send refund created email: {e}")
        
        email_thread = threading.Thread(target=send_email)
        email_thread.start()
        
        response_serializer = OrderRefundDetailSerializer(refund)
        return Response({
            'message': _('Refund request created successfully'),
            'refund': response_serializer.data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'], url_name='process-refund', url_path='process')
    def process_refund(self, request, pk=None):
        """
        Step 1: Process payment for refund (PENDING -> IN_PROGRESS).
        Sends payment via Stripe or initiates bank transfer.
        
        Request body:
        {
            "processing_notes": "Refund sent via bank transfer",
            "refund_method": "Bank Transfer",
            "bank_account_name": "John Doe",  // For manual refunds
            "bank_account_number": "12345678",
            "bank_sort_code": "12-34-56"
        }
        """
        refund = self.get_object()
        
        # Permission check
        if refund.event:
            if not has_event_permission(request.user, refund.event.id, 'can_approve_merch_payments'):
                return Response(
                    {'error': 'You do not have permission to process refunds for this event'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = ProcessOrderRefundSerializer(
            data=request.data,
            context={'refund': refund, 'request': request, 'action': 'process'}
        )
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        
        response_serializer = OrderRefundDetailSerializer(refund)
        return Response({
            'message': _('Refund payment sent. Please verify completion to finalize.'),
            'refund': response_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name='complete-refund', url_path='complete')
    def complete_refund(self, request, pk=None):
        """
        Step 2: Verify refund completion (IN_PROGRESS -> PROCESSED).
        Confirms payment was sent and restores stock.
        
        Request body:
        {
            "processing_notes": "Verified refund completed on 2024-01-15"
        }
        """
        refund = self.get_object()
        
        # Permission check
        if refund.event:
            if not has_event_permission(request.user, refund.event.id, 'can_approve_merch_payments'):
                return Response(
                    {'error': 'You do not have permission to complete refunds for this event'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        serializer = ProcessOrderRefundSerializer(
            data=request.data,
            context={'refund': refund, 'request': request, 'action': 'complete'}
        )
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        
        # Send confirmation email in background
        def send_email():
            try:
                from apps.shop.email_utils import send_order_refund_processed_email
                send_order_refund_processed_email(refund)
                logger.info(f"📧 Refund processed email sent for {refund.refund_reference}")
            except Exception as e:
                logger.error(f"⚠️ Failed to send refund processed email: {e}")
        
        email_thread = threading.Thread(target=send_email)
        email_thread.start()
        
        response_serializer = OrderRefundDetailSerializer(refund)
        return Response({
            'message': _('Refund completed successfully'),
            'refund': response_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name='cancel-refund', url_path='cancel')
    def cancel_refund(self, request, pk=None):
        """
        Cancel a refund request.
        
        Request body:
        {
            "cancellation_reason": "Customer withdrew request"
        }
        """
        refund = self.get_object()
        
        # Permission check
        if refund.event:
            if not has_event_permission(request.user, refund.event.id, 'can_approve_merch_payments'):
                return Response(
                    {'error': 'You do not have permission to cancel refunds for this event'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        cancellation_reason = request.data.get('cancellation_reason', 'Cancelled by administrator')
        
        refund_service = get_order_refund_service()
        success, message = refund_service.cancel_refund(refund, cancellation_reason)
        
        if success:
            response_serializer = OrderRefundDetailSerializer(refund)
            return Response({
                'message': message,
                'refund': response_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], url_name='retry-refund', url_path='retry')
    def retry_refund(self, request, pk=None):
        """
        Retry a failed refund.
        """
        refund = self.get_object()
        
        # Permission check
        if refund.event:
            if not has_event_permission(request.user, refund.event.id, 'can_approve_merch_payments'):
                return Response(
                    {'error': 'You do not have permission to retry refunds for this event'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        refund_service = get_order_refund_service()
        success, message = refund_service.retry_failed_refund(refund)
        
        if success:
            response_serializer = OrderRefundDetailSerializer(refund)
            return Response({
                'message': message,
                'refund': response_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_name='pending-refunds', url_path='pending')
    def pending_refunds(self, request):
        """
        Get all pending refunds (not yet processed).
        """
        queryset = self.get_queryset().filter(
            status__in=[
                OrderRefund.RefundStatus.PENDING,
                OrderRefund.RefundStatus.IN_PROGRESS
            ]
        )
        
        queryset = self.filter_queryset(queryset)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_name='statistics', url_path='statistics')
    def refund_statistics(self, request):
        """
        Get refund statistics for the requested scope.
        Only counts refunds where payment_amount > 0 (matching ParticipantRefund logic).
        """
        queryset = self.get_queryset()
        
        # Filter by event if specified
        event_id = request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event__id=event_id)
        
        # Only count refunds for paid orders (where refund_amount > 0)
        queryset = queryset.filter(refund_amount__gt=0)
        
        # Calculate statistics
        total_refunds = queryset.count()
        total_amount = queryset.aggregate(Sum('refund_amount'))['refund_amount__sum'] or 0
        
        status_counts = {}
        for choice in OrderRefund.RefundStatus.choices:
            status_key = choice[0]
            count = queryset.filter(status=status_key).count()
            status_counts[status_key] = count
        
        reason_counts = {}
        for choice in OrderRefund.RefundReason.choices:
            reason_key = choice[0]
            count = queryset.filter(refund_reason=reason_key).count()
            if count > 0:
                reason_counts[reason_key] = count
        
        avg_refund_amount = queryset.aggregate(models.Avg('refund_amount'))['refund_amount__avg'] or 0
        
        automatic_count = queryset.filter(is_automatic_refund=True).count()
        manual_count = queryset.filter(is_automatic_refund=False).count()
        
        stock_restored_count = queryset.filter(stock_restored=True).count()
        
        return Response({
            'total_refunds': total_refunds,
            'total_amount': float(total_amount),
            'average_amount': float(avg_refund_amount),
            'status_breakdown': status_counts,
            'reason_breakdown': reason_counts,
            'automatic_refunds': automatic_count,
            'manual_refunds': manual_count,
            'stock_restored_count': stock_restored_count,
        })
