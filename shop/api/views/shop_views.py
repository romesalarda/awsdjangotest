from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from shop.models.shop_models import EventProduct, EventCart, EventProductOrder
from shop.api.serializers.shop_serializers import (
    EventProductSerializer,
    EventCartSerializer,
    EventProductOrderSerializer,
)

class EventProductViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing event products.
    '''
    queryset = EventProduct.objects.prefetch_related("categories", "materials").select_related("event", "seller")
    serializer_class = EventProductSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["event", "size", "seller", "categories", "materials"]
    search_fields = ["title", "description", "seller__email"]
    ordering_fields = ["title", "price", "size", "discount"]
    ordering = ["title"]

class EventCartViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing event carts.
    '''
    queryset = EventCart.objects.select_related("user", "event").prefetch_related("products", "orders")
    serializer_class = EventCartSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["user", "event", "approved", "submitted", "active"]
    search_fields = ["user__email", "event__name", "notes", "shipping_address"]
    ordering_fields = ["created", "total", "shipping_cost"]
    ordering = ["-created"]

class EventProductOrderViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing orders of products within event carts.
    '''
    queryset = EventProductOrder.objects.select_related("product", "cart")
    serializer_class = EventProductOrderSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["product", "cart", "status"]
    search_fields = ["product__title", "cart__user__email"]
    ordering_fields = ["added", "quantity", "price_at_purchase", "discount_applied", "status"]
    ordering = ["-added"]