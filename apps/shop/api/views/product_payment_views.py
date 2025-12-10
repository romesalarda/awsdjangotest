from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.shop.models.payments import ProductPaymentMethod, ProductPaymentPackage, ProductPayment, EventProductOrder
from apps.shop.api.serializers.payment_serializers import (
    ProductPaymentMethodSerializer,
    ProductPaymentPackageSerializer,
    ProductPaymentSerializer,
)
from apps.shop.email_utils import send_payment_verified_email
import threading

class ProductPaymentMethodViewSet(viewsets.ModelViewSet):
    '''
    Product Payment Methods for event products
    '''
    queryset = ProductPaymentMethod.objects.all()
    serializer_class = ProductPaymentMethodSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["method", "account_name"]
    ordering_fields = ["created_at", "updated_at"]
    filterset_fields = ["event", "method", "is_active"]
    
    def get_queryset(self):
        """Filter payment methods based on user permissions and active status"""
        queryset = self.queryset
        
        # For non-admin users viewing available methods, only show active ones
        if not (self.request.user.is_superuser or getattr(self.request.user, 'is_encoder', False)):
            queryset = queryset.filter(is_active=True)
        
        return queryset

class ProductPaymentPackageViewSet(viewsets.ModelViewSet):
    '''
    Product Payment Packages for event products
    '''
    queryset = ProductPaymentPackage.objects.prefetch_related("products").all()
    serializer_class = ProductPaymentPackageSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "updated_at"]

class ProductPaymentViewSet(viewsets.ModelViewSet):
    '''
    Product Payments made by users for event products
    '''
    queryset = ProductPayment.objects.select_related("user", "cart", "package", "method").all()
    serializer_class = ProductPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__email", "cart__uuid", "status", "payment_reference_id"]
    ordering_fields = ["created_at", "amount", "status"]
    filterset_fields = ["cart__event", "method", "status", "approved"]
    
    def get_queryset(self):
        """Filter payments based on user permissions"""
        user = self.request.user
        if user.is_superuser or getattr(user, 'is_encoder', False):
            return self.queryset  # admins and encoders can see all payments
        return self.queryset.filter(user=user)  # regular users can only see their own payments
    
    @action(detail=True, methods=['post'], url_name='verify-payment', url_path='verify-payment', permission_classes=[permissions.IsAuthenticated])
    def verify_payment(self, request, pk=None):
        """
        Admin and authorized service team action to verify/approve a product payment.
        Marks payment as succeeded and approved, then sends confirmation email.
        
        SECURITY: Only staff, superusers, or service team with can_approve_merch_payments permission can verify.
        AUDIT: All payment verifications are logged for compliance.
        """
        payment = self.get_object()
        user = request.user
        
        # Check permissions: staff/superuser OR service team with can_approve_merch_payments
        from core.event_permissions import has_event_permission
        import logging
        logger = logging.getLogger(__name__)
        
        has_approval_permission = (
            user.is_staff or 
            user.is_superuser or 
            has_event_permission(user, payment.cart.event, 'can_approve_merch_payments')
        )
        
        if not has_approval_permission:
            from rest_framework.exceptions import PermissionDenied
            logger.warning(
                f"SECURITY: User {user.email} (ID: {user.id}) attempted to verify payment {payment.payment_reference_id} "
                f"without proper permissions. Request blocked."
            )
            raise PermissionDenied(
                "You do not have permission to verify payments. " + 
                "This action requires 'can_approve_merch_payments' permission or administrator access."
            )
        
        if payment.approved:
            logger.info(
                f"AUDIT: User {user.email} (ID: {user.id}) attempted to re-verify already verified payment "
                f"{payment.payment_reference_id}. No action taken."
            )
            return Response({
                "status": "already verified",
                "message": "This payment has already been verified."
            }, status=status.HTTP_200_OK)
        
        # Audit log before making changes
        logger.info(
            f"AUDIT: User {user.email} (ID: {user.id}, Staff: {user.is_staff}, Super: {user.is_superuser}) "
            f"verifying payment {payment.payment_reference_id} for cart {payment.cart.order_reference_id}. "
            f"Amount: {payment.currency.upper()} {payment.amount}"
        )
        
        # Use centralized payment completion logic
        was_completed = payment.complete_payment(log_metadata={
            'source': 'manual_verification',
            'verified_by': user.id,
            'verified_by_email': user.email
        })
        
        # Audit log after successful verification
        if was_completed:
            logger.info(
                f"AUDIT: Payment {payment.payment_reference_id} successfully verified by {user.email}. "
                f"Cart {payment.cart.order_reference_id} orders updated to PURCHASED status."
            )
        else:
            logger.info(
                f"AUDIT: Payment {payment.payment_reference_id} already completed, no changes made by {user.email}."
            )
        
        # Send confirmation email in background (only if newly completed)
        if was_completed:
            def send_email():
                try:
                    send_payment_verified_email(payment.cart, payment)
                    print(f"📧 Payment verification email queued for order {payment.cart.order_reference_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send payment verification email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()
        
        serializer = self.get_serializer(payment)
        return Response({
            "status": "payment verified",
            "message": f"Payment for order {payment.cart.order_reference_id} has been verified. Confirmation email sent to user.",
            "payment": serializer.data
        }, status=status.HTTP_200_OK)