"""
Serializers for order refund management.
Handles refund tracking, processing, and financial reconciliation for merchandise orders.
Supports both automatic (Stripe) and manual (bank transfer) refunds.
"""
from rest_framework import serializers
from apps.shop.models import OrderRefund, EventCart, ProductPayment, EventProduct, EventProductOrder
from apps.users.api.serializers import CommunityUserSerializer, SimplifiedCommunityUserSerializer
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class RefundCartSerializer(serializers.ModelSerializer):
    """Simplified cart info for refund display"""
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_code = serializers.CharField(source='event.event_code', read_only=True)
    order_items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EventCart
        fields = [
            'uuid',
            'order_reference_id',
            'total',
            'created',
            'event',
            'event_name',
            'event_code',
            'cart_status',
            'order_items_count'
        ]
    
    def get_order_items_count(self, obj):
        return obj.orders.count()


class OrderRefundListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for refund list views.
    Optimized for performance with minimal nested data.
    """
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.CharField(read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_code = serializers.CharField(source='event.event_code', read_only=True)
    cart_reference = serializers.CharField(source='cart.order_reference_id', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    refund_reason_display = serializers.CharField(source='get_refund_reason_display', read_only=True)
    days_pending = serializers.SerializerMethodField()
    can_process = serializers.SerializerMethodField()
    initiated_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderRefund
        fields = [
            'id',
            'refund_reference',
            'cart',
            'cart_reference',
            'customer_name',
            'customer_email',
            'event',
            'event_name',
            'event_code',
            'refund_amount',
            'currency',
            'status',
            'status_display',
            'refund_reason',
            'refund_reason_display',
            'reason_details',
            'is_automatic_refund',
            'refund_contact_email',
            'initiated_by_name',
            'stock_restored',
            'created_at',
            'processed_at',
            'days_pending',
            'can_process',
            'customer_notified',
            'admin_notified'
        ]
    
    def get_customer_name(self, obj):
        return obj.customer_name or (
            obj.user.get_full_name() if obj.user else "Unknown"
        )
    
    def get_days_pending(self, obj):
        """Calculate days since refund was created"""
        if obj.status == OrderRefund.RefundStatus.PROCESSED:
            return 0
        delta = timezone.now() - obj.created_at
        return delta.days
    
    def get_can_process(self, obj):
        can_process, message = obj.can_process_refund()
        return {
            'allowed': can_process,
            'message': message
        }
    
    def get_initiated_by_name(self, obj):
        if not obj.initiated_by:
            return "Customer"
        return obj.initiated_by.get_full_name() if hasattr(obj.initiated_by, 'get_full_name') else obj.initiated_by.email


class OrderRefundDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for detailed refund views.
    Includes full cart, payment, and processing information.
    """
    cart = RefundCartSerializer(read_only=True)
    initiated_by_name = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    refund_reason_display = serializers.CharField(source='get_refund_reason_display', read_only=True)
    can_process = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()
    order_items = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderRefund
        fields = [
            'id',
            'refund_reference',
            'cart',
            'payment',
            'user',
            'event',
            'refund_amount',
            'currency',
            'status',
            'status_display',
            'refund_reason',
            'refund_reason_display',
            'reason_details',
            'initiated_by',
            'initiated_by_name',
            'processed_by',
            'processed_by_name',
            'processing_notes',
            'customer_email',
            'customer_name',
            'refund_contact_email',
            'original_payment_method',
            'is_automatic_refund',
            'refund_method',
            'stripe_payment_intent',
            'stripe_refund_id',
            'stripe_failure_reason',
            'stock_restored',
            'stock_restored_at',
            'customer_notified',
            'admin_notified',
            'created_at',
            'updated_at',
            'processed_at',
            'can_process',
            'payment_details',
            'order_items',
            'timeline'
        ]
        read_only_fields = [
            'refund_reference',
            'initiated_by',
            'created_at',
            'updated_at'
        ]
    
    def get_initiated_by_name(self, obj):
        if not obj.initiated_by:
            return "Customer"
        return obj.initiated_by.get_full_name() if hasattr(obj.initiated_by, 'get_full_name') else obj.initiated_by.email
    
    def get_processed_by_name(self, obj):
        if not obj.processed_by:
            return None
        return obj.processed_by.get_full_name() if hasattr(obj.processed_by, 'get_full_name') else obj.processed_by.email
    
    def get_can_process(self, obj):
        can_process, message = obj.can_process_refund()
        return {
            'allowed': can_process,
            'message': message
        }
    
    def get_payment_details(self, obj):
        """Get detailed information about original payment"""
        if not obj.payment:
            return None
        
        return {
            'id': obj.payment.id,
            'reference': obj.payment.payment_reference_id,
            'amount': float(obj.payment.amount),
            'payment_method': obj.payment.method.get_method_display() if obj.payment.method else None,
            'stripe_payment_intent': obj.payment.stripe_payment_intent,
            'paid_at': obj.payment.paid_at,
            'status': obj.payment.get_status_display()
        }
    
    def get_order_items(self, obj):
        """Get list of products in the order"""
        if not obj.cart:
            return []
        
        orders = EventProductOrder.objects.filter(cart=obj.cart).select_related('product', 'size')
        return [
            {
                'id': order.id,
                'product_title': order.product.title if order.product else "Unknown",
                'product_id': order.product.uuid if order.product else None,
                'quantity': order.quantity,
                'size': order.size.size if order.size else None,
                'color': order.product.colors if order.product else None,
                'price': float(order.price_at_purchase),
                'subtotal': float(order.price_at_purchase * order.quantity)
            }
            for order in orders
        ]
    
    def get_timeline(self, obj):
        """Generate timeline of refund events"""
        timeline = [
            {
                'event': 'Refund Created',
                'timestamp': obj.created_at,
                'by': self.get_initiated_by_name(obj),
                'status': 'PENDING',
                'notes': obj.reason_details[:100] if obj.reason_details else None
            }
        ]
        
        if obj.status == OrderRefund.RefundStatus.IN_PROGRESS:
            timeline.append({
                'event': 'Refund In Progress',
                'timestamp': obj.updated_at,
                'status': 'IN_PROGRESS'
            })
        
        if obj.stock_restored:
            timeline.append({
                'event': 'Stock Restored',
                'timestamp': obj.stock_restored_at,
                'status': 'INFO'
            })
        
        if obj.processed_at:
            timeline.append({
                'event': 'Refund Processed',
                'timestamp': obj.processed_at,
                'by': self.get_processed_by_name(obj),
                'status': 'PROCESSED',
                'notes': obj.processing_notes[:100] if obj.processing_notes else None
            })
        
        if obj.status == OrderRefund.RefundStatus.FAILED:
            timeline.append({
                'event': 'Refund Failed',
                'timestamp': obj.updated_at,
                'status': 'FAILED',
                'notes': obj.stripe_failure_reason
            })
        
        return timeline

class SimpleOrderRefundSerializer(serializers.ModelSerializer):
    """Simple serializer for basic refund info"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    refund_reason_display = serializers.CharField(source='get_refund_reason_display', read_only=True)
    user = SimplifiedCommunityUserSerializer(read_only=True)
    class Meta:
        model = OrderRefund
        fields = [
            'id',
            'refund_reference',
            'refund_amount',
            'currency',
            'status',
            'status_display',
            'refund_reason',
            'refund_reason_display',
            'is_automatic_refund',
            'created_at',
            'original_payment_method',
            'user',
        ]

class CreateOrderRefundSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new order refund records.
    Used when initiating refunds from UI.
    """
    
    class Meta:
        model = OrderRefund
        fields = [
            'cart',
            'payment',
            'user',
            'event',
            'refund_amount',
            'refund_reason',
            'reason_details',
            'initiated_by',
            'customer_email',
            'customer_name',
            'refund_contact_email',
            'original_payment_method',
            'is_automatic_refund',
            'stripe_payment_intent',
        ]
        read_only_fields = ['initiated_by']
    
    def validate(self, data):
        """Validate refund data"""
        cart = data.get('cart')
        refund_amount = data.get('refund_amount', Decimal('0.00'))
        
        # Ensure cart exists and has valid status
        if not cart:
            raise serializers.ValidationError({
                'cart': "Cart is required"
            })
        
        if cart.cart_status not in ['completed', 'locked']:
            # Allow submitted/paid/fulfilled carts to be refunded
            if not (cart.submitted or cart.approved):
                raise serializers.ValidationError({
                    'cart': "Only submitted or paid orders can be refunded"
                })
        
        # Check if cart already has an active refund
        existing_refund = OrderRefund.objects.filter(
            cart=cart,
            status__in=[
                OrderRefund.RefundStatus.PENDING,
                OrderRefund.RefundStatus.IN_PROGRESS
            ]
        ).first()
        
        if existing_refund:
            raise serializers.ValidationError({
                'cart': f"This order already has an active refund request: {existing_refund.refund_reference}"
            })
        
        # Check if cart was already refunded
        processed_refund = OrderRefund.objects.filter(
            cart=cart,
            status=OrderRefund.RefundStatus.PROCESSED
        ).first()
        
        if processed_refund:
            raise serializers.ValidationError({
                'cart': f"This order was already refunded: {processed_refund.refund_reference}"
            })
        
        # Validate refund amount
        if refund_amount <= 0:
            raise serializers.ValidationError({
                'refund_amount': "Refund amount must be greater than zero"
            })
        
        if cart.total and refund_amount > Decimal(str(cart.total)):
            raise serializers.ValidationError({
                'refund_amount': f"Refund amount cannot exceed cart total (£{cart.total})"
            })
        
        # Check refund eligibility
        event = data.get('event') or cart.event
        if event:
            refund_deadline = getattr(event, 'refund_deadline', None) or getattr(event, 'payment_deadline', None)
            if refund_deadline and timezone.now() > refund_deadline:
                # Allow but add warning flag (admin can override)
                data['_deadline_warning'] = True
        
        return data
    
    def create(self, validated_data):
        """Create refund and set default values"""
        validated_data.pop('_deadline_warning', None)  # Remove warning flag
        
        # Set customer details from cart if not provided
        cart = validated_data['cart']
        if not validated_data.get('customer_email') and cart.user:
            validated_data['customer_email'] = cart.user.primary_email if hasattr(cart.user, 'primary_email') else cart.user.email
        
        if not validated_data.get('customer_name') and cart.user:
            validated_data['customer_name'] = cart.user.get_full_name() if hasattr(cart.user, 'get_full_name') else str(cart.user)
        
        # Set refund contact email from payment method if available
        if not validated_data.get('refund_contact_email'):
            payment = validated_data.get('payment')
            if payment and payment.method:
                validated_data['refund_contact_email'] = payment.method.refund_contact_email or getattr(cart.event, 'secretariat_email', None)
        
        refund = super().create(validated_data)
        return refund


class ProcessOrderRefundSerializer(serializers.Serializer):
    """
    Serializer for processing refund completion.
    Validates refund processing data and updates status.
    
    NOTE: Bank account details should NEVER be collected or stored.
    Manual refunds should be processed outside the system through secure banking channels.
    """
    processing_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional notes about the refund processing"
    )
    refund_method = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Method used to process the refund (e.g., 'Bank Transfer', 'Stripe')"
    )
    restore_stock = serializers.BooleanField(
        default=True,
        help_text="Whether to restore product stock upon processing refund"
    )
    
    def validate(self, data):
        """Ensure refund can be processed"""
        refund = self.context.get('refund')
        action = self.context.get('action', 'process')  # 'process' or 'complete'
        
        if not refund:
            raise serializers.ValidationError("Refund instance required in context")
        
        if action == 'complete':
            # Completing refund (IN_PROGRESS -> PROCESSED)
            if refund.status != OrderRefund.RefundStatus.IN_PROGRESS:
                raise serializers.ValidationError("Can only complete refunds that are IN_PROGRESS")
        else:
            # Processing refund (PENDING -> IN_PROGRESS)
            can_process, message = refund.can_process_refund()
            if not can_process:
                raise serializers.ValidationError(message)
            
            if refund.status not in [OrderRefund.RefundStatus.PENDING]:
                raise serializers.ValidationError(f"Refund is already {refund.status}")
        
        # For manual refunds, processing notes are recommended but not required
        # Bank transfers should be handled outside the system for security
        
        return data
    
    def save(self):
        """Process or complete the refund based on action"""
        refund = self.context['refund']
        user = self.context['request'].user
        action = self.context.get('action', 'process')  # 'process' or 'complete'
        
        if action == 'complete':
            # Complete refund: IN_PROGRESS -> PROCESSED
            from apps.shop.services.order_refund_service import get_order_refund_service
            refund_service = get_order_refund_service()
            success, message = refund_service.complete_manual_refund(
                refund,
                self.validated_data.get('processing_notes')
            )
            if not success:
                raise serializers.ValidationError(message)
        else:
            # Process refund: PENDING -> IN_PROGRESS
            from apps.shop.services.order_refund_service import get_order_refund_service
            refund_service = get_order_refund_service()
            
            if refund.is_automatic_refund:
                success, message = refund_service.process_automatic_refund(refund)
            else:
                # Save refund method for tracking (but never bank account details)
                if self.validated_data.get('refund_method'):
                    refund.refund_method = self.validated_data['refund_method']
                refund.save()
                
                success, message = refund_service.process_manual_refund(
                    refund,
                    self.validated_data.get('processing_notes')
                )
            
            if not success:
                raise serializers.ValidationError(message)
        
        return refund
