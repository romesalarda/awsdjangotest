from rest_framework import viewsets, permissions, filters, serializers, exceptions
from rest_framework.response import Response
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, models
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder
from apps.shop.models.metadata_models import ProductSize
from apps.shop.models.payments import ProductPaymentMethod, ProductPayment
from apps.shop.api.serializers.shop_serializers import (
    EventProductSerializer,
    EventCartSerializer,
    EventProductOrderSerializer,
)
from apps.shop.api.serializers.shop_metadata_serializers import ProductSizeSerializer
from apps.shop.api.serializers.payment_serializers import ProductPaymentMethodSerializer

class EventProductViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing event products.
    '''
    queryset = EventProduct.objects.prefetch_related("categories", "materials").select_related("event", "seller")
    serializer_class = EventProductSerializer
    permission_classes = [permissions.IsAuthenticated]  # Allow authenticated users to manage products
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["event", "seller", "categories", "materials", "category", "featured", "in_stock"]
    search_fields = ["title", "description", "seller__email", "category"]
    ordering_fields = ["title", "price", "discount", "stock", "featured"]
    ordering = ["title"]
    
    def get_queryset(self):
        # TODO: add filters to show products via search queries
        user = self.request.user
        # if user.is_superuser:
        #     return self.queryset
        return self.queryset
    
    def perform_create(self, serializer):
        """Set the seller to the current user when creating a product"""
        serializer.save(seller=self.request.user)
    
    def perform_update(self, serializer):
        """Handle product updates"""
        serializer.save()
    
    @action(detail=True, methods=['get'], url_name='sizes', url_path='sizes')
    def available_sizes(self, request, pk=None):
        '''
        Retrieve available sizes for a specific event product.
        '''
        product = self.get_object()
        sizes = product.product_sizes_set.all()
        page = self.paginate_queryset(sizes)
        if page is not None:
            serializer = ProductSizeSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductSizeSerializer(sizes, many=True)
        return Response(serializer.data)

class EventCartViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing event carts.
    '''
    queryset = EventCart.objects.select_related("user", "event").prefetch_related("products", "orders")
    serializer_class = EventCartSerializer
    permission_classes = [permissions.IsAuthenticated] # only admins can see all carts
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["user", "event", "approved", "submitted", "active"]
    search_fields = ["user__email", "event__name", "notes", "shipping_address"]
    ordering_fields = ["created", "total", "shipping_cost"]
    ordering = ["-created"]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or getattr(user, 'is_encoder', False):
            return self.queryset  # admins and encoders can see all carts
        return self.queryset.filter(user=user)  # regular users can only see their own carts
    
    @action(detail=True, methods=['post'], url_name='add', url_path='add')
    def add_to_cart(self, request, *args, **kwargs):
        '''
        Bulk add products to the cart.
        E.g. {"products": [{"product_id": "uuid1", "quantity": 2, "size": "M"}, {"product_id": "uuid2", "quantity": 1}]}
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user can modify this cart
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only modify your own carts.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")
        
        products = request.data.get("products", [])
        
        if not products:
            raise serializers.ValidationError("No products provided to add to cart.")
        # {product_id: ..., quantity: ..., size: ...}
        
        for product in products:

            product_id = product.get("uuid")
            quantity = product.get("quantity", 1)
            size = product.get("size", None)
            
            product_object = get_object_or_404(EventProduct, uuid=product_id)
            # ensure product belongs to the same event as the cart
            if product_object.event != cart.event:
                raise serializers.ValidationError(f"Product {product_object.title} does not belong to the same event as the cart.")
            # check size is valid for product
            if size:
                size_object = ProductSize.objects.filter(size=size, product=product_object).first()
                if not size_object:
                    raise serializers.ValidationError(f"Size {size} not available for product {product_object.title}")
            else:
                size_object = None
            # create an order but ensure it does not already exist for this product in the cart
            order, created = EventProductOrder.objects.get_or_create(
                product=product_object,
                cart=cart,
                quantity=quantity,
                size=size_object
            )    
            if not created:
                raise serializers.ValidationError(f"Order for product {product_object.title} already exists in cart.")
            order.save()
            cart.products.add(product_object)
            cart.orders.add(order)
            
        # update cart information
        total = 0
        for order in cart.orders.all():
            total += (order.price_at_purchase or order.product.price) * order.quantity
            
        cart.total = total
        cart.save()     
        serialized = self.get_serializer(cart)
        return Response({"status": "cart added" if len(products) > 0 else "no changes", "product": serialized.data}, status=200)

    @action(detail=True, methods=['post'], url_name='remove', url_path='remove')
    def remove_from_cart(self, request, *args, **kwargs):
        '''
        Bulk remove products from the cart.
        E.g. {"products": ["product_uuid1", "product_uuid2"]}
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user can modify this cart
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only modify your own carts.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")
        
        products = request.data.get("products", [])
        
        if not products:
            raise serializers.ValidationError("No products provided to remove from cart.")
        for prod_id in products:
            product = get_object_or_404(EventProduct, uuid=prod_id)
            cart.products.remove(product)
            orders = EventProductOrder.objects.filter(cart=cart, product=product)
            orders.delete()  # check if it was removed

        cart.save()
        
        serialized = self.get_serializer(cart)
        return Response({"status": "product removed" if len(products) > 0 else "no changes", "product": serialized.data}, status=200)
        
    @action(detail=True, methods=['post'], url_name='checkout', url_path='checkout')
    def checkout_cart(self, request, *args, **kwargs):
        '''
        Process cart checkout with payment method validation and payment tracking.
        Expected payload: {
            "payment_method_id": 1,
            "amount": 125.50  // Amount in pounds, optional - will be validated against cart total
        }
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user owns this cart or has admin permissions
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only checkout your own carts.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot checkout an approved or submitted cart.")
        
        if not cart.orders.exists():
            raise serializers.ValidationError("Cannot checkout an empty cart.")
            
        # Get and validate payment method
        payment_method_id = request.data.get('payment_method_id')
        if not payment_method_id:
            raise serializers.ValidationError("Payment method is required for checkout.")
            
        try:
            payment_method = ProductPaymentMethod.objects.get(
                id=payment_method_id,
                is_active=True
            )
        except ProductPaymentMethod.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive payment method.")
        
        # Validate payment method is available for this event
        if payment_method.event and payment_method.event != cart.event:
            raise serializers.ValidationError(
                f"Payment method '{payment_method.get_method_display()}' is not available for this event."
            )
        
        # Calculate and validate cart total
        calculated_total = 0
        for order in cart.orders.all():
            if not order.product.in_stock:
                raise serializers.ValidationError(
                    f"Product '{order.product.title}' is no longer in stock."
                )
            calculated_total += (order.price_at_purchase or order.product.price) * order.quantity
        
        # Keep total in decimal format (pounds)
        calculated_total_decimal = calculated_total
        
        # Validate provided amount if given
        provided_amount = request.data.get('amount')
        if provided_amount is not None:
            if provided_amount != calculated_total_decimal:
                raise serializers.ValidationError(
                    f"Provided amount (£{provided_amount:.2f}) does not match cart total (£{calculated_total_decimal:.2f})."
                )
        
        # Use atomic transaction for checkout process
        with transaction.atomic():
            # Create payment record
            payment = ProductPayment.objects.create(
                user=cart.user,
                cart=cart,
                method=payment_method,
                amount=calculated_total_decimal,
                currency=getattr(cart.event, 'currency', 'gbp'),
                status=ProductPayment.PaymentStatus.PENDING
            )
            
            # Update cart status
            cart.submitted = True
            cart.active = False
            cart.total = calculated_total  # Ensure total is correctly set
            cart.save()
            
            # For non-Stripe payments, they might need manual approval
            if payment_method.method == ProductPaymentMethod.MethodType.STRIPE:
                # Stripe payments will be handled by webhook/frontend
                payment_status = "Payment intent created - complete payment on frontend"
            else:
                payment_status = f"Payment recorded - please follow {payment_method.get_method_display()} instructions"
        
        # Get detailed instructions for bank transfers
        instructions = payment_method.instructions
        if payment_method.method == ProductPaymentMethod.MethodType.BANK_TRANSFER:
            bank_instructions = payment.get_bank_transfer_instructions()
            if bank_instructions:
                instructions = bank_instructions

        serialized = self.get_serializer(cart)
        return Response({
            "status": "cart checkout successful", 
            "cart": serialized.data,
            "payment": {
                "id": payment.id,
                "reference_id": payment.payment_reference_id,
                "bank_reference": payment.bank_reference,
                "method": payment_method.get_method_display(),
                "amount": calculated_total_decimal,
                "currency": payment.currency,
                "status": payment.get_status_display(),
                "instructions": instructions
            },
            "message": payment_status
        }, status=200)

    @action(detail=True, methods=['patch'], url_name='update', url_path='update-order')
    def update_cart(self, request, *args, **kwargs):
        '''
        Replace cart products/orders with provided list.
        Returns a summary of changes.
        E.g. {"products": [{"id": "uuid1", "quantity": 2, "size": "M"}, {"id": "uuid2", "quantity": 1}]}
        '''
        cart: EventCart = self.get_object()
        products = request.data.get("products", [])
        
        self.check_object_permissions(request, cart)
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")

        # Detect duplicates in incoming products
        seen = set()
        duplicates = []
        for prod in products:
            key = (prod.get("id"), prod.get("size", None))
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        if duplicates:
            raise serializers.ValidationError(
                f"Duplicate product and size combinations detected: {', '.join([f'{pid} (size: {size})' for pid, size in duplicates])}"
            )

        new_product_keys = set(
            (p["id"], p.get("size", None)) for p in products
        )

        removed_products = []
        updated_orders = []
        added_orders = []

        # Remove orders not in new list (compare product and size)
        for order in list(cart.orders.all()):
            key = (str(order.product.uuid), order.size.size if order.size else None)
            if key not in new_product_keys:
                removed_products.append(
                    f"Removed {order.product.title} (size: {order.size.size if order.size else 'N/A'})"
                )
                # cart.products.remove(order.product)
                order.delete()

        # Add/update products/orders from new list
        for prod in products:
            product_id = prod.get("id")
            quantity = prod.get("quantity", 1)
            size = prod.get("size", None)

            product_object = get_object_or_404(EventProduct, uuid=product_id)
            if product_object.event != cart.event:
                raise serializers.ValidationError(
                    f"Product {product_object.title} does not belong to the same event as the cart."
                )

            size_object = None
            if size:
                size_object = ProductSize.objects.filter(size=size, product=product_object).first()
                if not size_object:
                    raise serializers.ValidationError(
                        f"Size {size} not available for product {product_object.title}"
                    )

            # Only look for existing order by product, cart, size
            order = EventProductOrder.objects.filter(
                product=product_object,
                cart=cart,
                size=size_object
            ).first()
            
            if quantity > product_object.maximum_order_quantity:
                raise serializers.ValidationError(
                    f"Quantity {quantity} exceeds maximum order quantity of {product_object.maximum_order_quantity} for product {product_object.title}"
                )
            order.price_at_purchase = product_object.price
            if order:
                # Update quantity if changed
                if order.quantity != quantity:
                    order.quantity = quantity
                    order.save()
                    updated_orders.append(
                        f"Updated {product_object.title} (size: {size_object.size if size_object else 'N/A'}, quantity: {quantity})"
                    )
            else:
                # Create new order only if not found
                order, created = EventProductOrder.objects.get_or_create(
                    product=product_object,
                    cart=cart,
                    quantity=quantity,
                    size=size_object
                )
                if created:
                    added_orders.append(
                        f"Added {product_object.title} (size: {size_object.size if size_object else 'N/A'}, quantity: {quantity})"
                    )
            # cart.products.add(product_object) # add if not already present
            cart.orders.add(order)

        # Recalculate total
        total = 0
        for order in cart.orders.all():
            total += (order.price_at_purchase or order.product.price) * order.quantity
        cart.total = total
        cart.save()

        summary = []
        if removed_products:
            summary.extend(removed_products)
        if updated_orders:
            summary.extend(updated_orders)
        if added_orders:
            summary.extend(added_orders)
        if not summary:
            summary.append("No changes to cart.")

        return Response({"status": "cart updated", "changes": summary}, status=200)

    @action(detail=True, methods=['post'], url_name='clear', url_path='clear')
    def clear_cart(self, request, *args, **kwargs):
        '''
        Clear all products and orders from the cart.
        '''
        cart: EventCart = self.get_object()
        self.check_object_permissions(request, cart)
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")
        
        cart.products.clear()
        cart.orders.all().delete()
        cart.total = 0
        cart.save()
        serialized = self.get_serializer(cart)
        return Response({"status": "cart cleared", "cart": serialized.data}, status=200)
    
    @action(detail=True, methods=['get'], url_name='payment-methods', url_path='payment-methods')
    def get_payment_methods(self, request, *args, **kwargs):
        '''
        Get available payment methods for this cart's event.
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user can view this cart
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only view your own cart's payment methods.")
        
        # Get payment methods for this event (or global ones)
        payment_methods = ProductPaymentMethod.objects.filter(
            is_active=True
        ).filter(
            models.Q(event=cart.event) | models.Q(event__isnull=True)
        ).order_by('method')
        
        serializer = ProductPaymentMethodSerializer(payment_methods, many=True)
        return Response({
            "payment_methods": serializer.data,
            "event": cart.event.name if cart.event else "No event"
        }, status=200)
    


class EventProductOrderViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing orders of products within event carts.
    '''
    queryset = EventProductOrder.objects.select_related("product", "cart")
    serializer_class = EventProductOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["product", "cart", "status"]
    search_fields = ["product__title", "cart__user__email"]
    ordering_fields = ["added", "quantity", "price_at_purchase", "discount_applied", "status"]
    ordering = ["-added"]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or getattr(user, 'is_encoder', False):
            return self.queryset  # admins and encoders can see all orders
        return self.queryset.filter(cart__user=user)  # regular users can only see their own orders