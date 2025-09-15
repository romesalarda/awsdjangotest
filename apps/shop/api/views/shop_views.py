from rest_framework import viewsets, permissions, filters
from rest_framework.response import Response
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder
from apps.shop.api.serializers.shop_serializers import (
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
    
    @action(detail=True, methods=['post'], url_name='add', url_path='add')
    def add_to_cart(self, request, *args, **kwargs):
        # Logic to add a product to the cart
        cart: EventCart = self.get_object()
        
        products = request.data.get("products", [])
        for prod_id in products:
            product = get_object_or_404(EventProduct, uuid=prod_id)
            cart.products.add(product)

        cart.save()
        
        serialized = self.get_serializer(cart)
        return Response({"status": "product added" if len(products) > 0 else "no changes", "product": serialized.data}, status=200)

    @action(detail=True, methods=['post'], url_name='remove', url_path='remove')
    def remove_from_cart(self, request, *args, **kwargs):
        # Logic to remove a product from the cart
        cart: EventCart = self.get_object()
        
        products = request.data.get("products", [])
        for prod_id in products:
            product = get_object_or_404(EventProduct, uuid=prod_id)
            cart.products.remove(product)
            orders = EventProductOrder.objects.filter(cart=cart, product=product)
            orders.delete()  # remove any associated orders as well

        cart.save()
        
        serialized = self.get_serializer(cart)
        return Response({"status": "product removed" if len(products) > 0 else "no changes", "product": serialized.data}, status=200)

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
    