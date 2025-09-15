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
    search_fields = ["user__email", "cart__uuid", "status"]
    ordering_fields = ["created_at", "amount", "status"]