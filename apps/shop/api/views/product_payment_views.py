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
    
    @action(detail=True, methods=['post'], url_name='verify-payment', url_path='verify-payment', permission_classes=[permissions.IsAdminUser])
    def verify_payment(self, request, pk=None):
        """
        Admin action to verify/approve a product payment.
        Marks payment as succeeded and approved, then sends confirmation email.
        """
        payment = self.get_object()
        
        if payment.approved:
            return Response({
                "status": "already verified",
                "message": "This payment has already been verified."
            }, status=status.HTTP_200_OK)
        
        # Update payment status
        payment.status = ProductPayment.PaymentStatus.SUCCEEDED
        payment.approved = True
        payment.mark_as_paid()
        payment.save()
        
        # todo: all orders must be set to approved as well
        for order in payment.cart.orders.all():
            order.status = EventProductOrder.Status.PURCHASED
            order.save()
        
        # Send confirmation email in background
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