from rest_framework import viewsets, permissions, filters
from apps.shop.models.payments import ProductPaymentMethod, ProductPaymentPackage, ProductPayment
from apps.shop.api.serializers.payment_serializers import (
    ProductPaymentMethodSerializer,
    ProductPaymentPackageSerializer,
    ProductPaymentSerializer,
)

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