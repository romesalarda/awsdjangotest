from rest_framework import viewsets, permissions, filters, serializers, exceptions
from rest_framework.response import Response
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, models
from datetime import timedelta
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder, ProductPurchaseTracker
from apps.shop.models.metadata_models import ProductSize
from apps.shop.models.payments import ProductPaymentMethod, ProductPayment, ProductPaymentLog
from apps.shop.api.serializers.shop_serializers import (
    EventProductSerializer,
    EventCartSerializer,
    EventProductOrderSerializer,
)
from apps.shop.api.serializers.shop_metadata_serializers import ProductSizeSerializer
from apps.shop.api.serializers.payment_serializers import ProductPaymentMethodSerializer
from apps.shop.email_utils import send_order_confirmation_email
import threading

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
    
    def get_serializer_context(self):
        """Add request to serializer context for user-specific pricing"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
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
        # if user.is_superuser or getattr(user, 'is_encoder', False):
        #     return self.queryset  # admins and encoders can see all carts
        return self.queryset.filter(user=user)  # regular users can only see their own carts
    
    @action(detail=True, methods=['post'], url_name='add', url_path='add')
    def add_to_cart(self, request, *args, **kwargs):
        '''
        Bulk add products to the cart with max purchase validation and stock locking.
        E.g. {"products": [{"product_id": "uuid1", "quantity": 2, "size": "M"}, {"product_id": "uuid2", "quantity": 1}]}
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user can modify this cart
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only modify your own carts.")
        
        # Check if user can purchase merch for this event
        can_purchase, reason = cart.event.can_purchase_merch(cart.user)
        if not can_purchase:
            raise serializers.ValidationError(reason)
        
        # Check cart status
        if cart.cart_status in [EventCart.CartStatus.LOCKED, EventCart.CartStatus.COMPLETED]:
            raise serializers.ValidationError("Cannot modify a locked or completed cart.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")
        
        products = request.data.get("products", [])
        
        if not products:
            raise serializers.ValidationError("No products provided to add to cart.")
        
        # Use atomic transaction with row-level locking for concurrency safety
        with transaction.atomic():
            added_products = []
            
            for product in products:
                product_id = product.get("uuid")
                quantity = product.get("quantity", 1)
                size = product.get("size", None)
                
                # Lock the product row for update to prevent race conditions
                product_object = EventProduct.objects.select_for_update().get(uuid=product_id)
                
                # Ensure product belongs to the same event as the cart
                if product_object.event != cart.event:
                    raise serializers.ValidationError(
                        f"Product {product_object.title} does not belong to the same event as the cart."
                    )
                
                # Check stock availability
                if product_object.stock < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product_object.title}. Available: {product_object.stock}, Requested: {quantity}"
                    )
                
                # Check max purchase per person limit
                can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                    user=cart.user,
                    product=product_object,
                    quantity=quantity
                )
                
                if not can_purchase:
                    raise serializers.ValidationError(error_msg)
                
                # Check size is valid for product
                size_object = None
                if size:
                    size_object = ProductSize.objects.filter(size=size, product=product_object).first()
                    if not size_object:
                        raise serializers.ValidationError(
                            f"Size {size} not available for product {product_object.title}"
                        )
                
                # Check if order already exists for this product in the cart
                existing_order = EventProductOrder.objects.filter(
                    product=product_object,
                    cart=cart,
                    size=size_object
                ).first()
                
                # Calculate discount for service team members
                from decimal import Decimal
                original_price = Decimal(str(product_object.price))
                discounted_price = product_object.get_price_for_user(cart.user)
                discount_amount = original_price - discounted_price
                
                if existing_order:
                    # Update existing order quantity instead of throwing error
                    new_quantity = existing_order.quantity + quantity
                    
                    # Re-check max purchase limit with new quantity
                    can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                        user=cart.user,
                        product=product_object,
                        quantity=new_quantity - existing_order.quantity  # Only check the additional quantity
                    )
                    
                    if not can_purchase:
                        raise serializers.ValidationError(error_msg)
                    
                    # Check stock for additional quantity
                    if product_object.stock < quantity:
                        raise serializers.ValidationError(
                            f"Insufficient stock for additional {product_object.title}. Available: {product_object.stock}, Requested: {quantity}"
                        )
                    
                    existing_order.quantity = new_quantity
                    existing_order.price_at_purchase = discounted_price
                    existing_order.discount_applied = discount_amount if discount_amount > 0 else Decimal('0')
                    existing_order.save()
                    
                    added_products.append({
                        'product': product_object.title,
                        'quantity': quantity,
                        'size': size_object.size if size_object else None,
                        'updated': True,
                        'total_quantity': new_quantity
                    })
                else:
                    # Create the order with discount information
                    order = EventProductOrder.objects.create(
                        product=product_object,
                        cart=cart,
                        quantity=quantity,
                        size=size_object,
                        price_at_purchase=discounted_price,
                        discount_applied=discount_amount if discount_amount > 0 else Decimal('0')
                    )
                    
                    cart.products.add(product_object)
                    added_products.append({
                        'product': product_object.title,
                        'quantity': quantity,
                        'size': size_object.size if size_object else None,
                        'updated': False
                    })
            
            # Update cart total
            total = 0
            for order in cart.orders.all():
                total += (order.price_at_purchase or order.product.price) * order.quantity
                
            cart.total = total
            cart.save()
        
        serialized = self.get_serializer(cart)
        return Response({
            "status": "products added to cart",
            "added": added_products,
            "cart": serialized.data
        }, status=200)

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
        
        # Check cart status
        if cart.cart_status in [EventCart.CartStatus.LOCKED, EventCart.CartStatus.COMPLETED]:
            raise serializers.ValidationError(f"Cannot modify a {cart.cart_status} cart.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot modify an approved or submitted cart.")
        
        products = request.data.get("products", [])
        
        if not products:
            raise serializers.ValidationError("No products provided to remove from cart.")
        
        with transaction.atomic():
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
        Process cart checkout with payment method validation, cart locking, inventory reservation, and contact info.
        Expected payload: {
            "payment_method_id": 1,
            "amount": 125.50,  // Amount in pounds, optional - will be validated against cart total
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "+44123456789"
        }
        '''
        cart: EventCart = self.get_object()
        
        # Security check: ensure user owns this cart or has admin permissions
        self.check_object_permissions(request, cart)
        if not (cart.user == request.user or request.user.is_superuser or getattr(request.user, 'is_encoder', False)):
            raise exceptions.PermissionDenied("You can only checkout your own carts.")
        
        # Check cart status
        if cart.cart_status in [EventCart.CartStatus.COMPLETED, EventCart.CartStatus.EXPIRED]:
            raise serializers.ValidationError(f"Cannot checkout a {cart.cart_status} cart.")
        
        if cart.cart_status == EventCart.CartStatus.LOCKED:
            # Check if lock has expired
            if cart.lock_expires_at and timezone.now() > cart.lock_expires_at:
                cart.cart_status = EventCart.CartStatus.EXPIRED
                cart.save()
                raise serializers.ValidationError("Cart lock has expired. Please try again.")
            raise serializers.ValidationError("Cart is currently locked for checkout.")
        
        if cart.approved or cart.submitted:
            raise serializers.ValidationError("Cannot checkout an approved or submitted cart.")
        
        if not cart.orders.exists():
            raise serializers.ValidationError("Cannot checkout an empty cart.")
        
        # Extract contact information
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        email = request.data.get('email', '').strip()
        phone = request.data.get('phone', '').strip()
        
        # Validate contact info
        if not first_name or not last_name:
            raise serializers.ValidationError("First name and last name are required.")
        if not email:
            raise serializers.ValidationError("Email is required for order confirmation.")
        
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
        
        # Use atomic transaction with row-level locking for checkout process
        with transaction.atomic():
            # Lock the cart
            cart = EventCart.objects.select_for_update().get(pk=cart.pk)
            
            # Re-check status after acquiring lock
            if cart.cart_status != EventCart.CartStatus.ACTIVE:
                raise serializers.ValidationError(f"Cart status changed to {cart.cart_status}. Cannot proceed.")
            
            # Lock cart for 15 minutes
            cart.cart_status = EventCart.CartStatus.LOCKED
            cart.locked_at = timezone.now()
            cart.lock_expires_at = timezone.now() + timedelta(minutes=15)
            cart.save()
            
            # Calculate and validate cart total with stock checks
            calculated_total = 0
            stock_issues = []
            
            for order in cart.orders.select_related('product').select_for_update():
                product = order.product
                
                # Check stock availability
                if not product.in_stock or product.stock < order.quantity:
                    stock_issues.append(
                        f"{product.title} (requested: {order.quantity}, available: {product.stock})"
                    )
                    continue
                
                # Check max purchase limit hasn't been exceeded
                can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                    user=cart.user,
                    product=product,
                    quantity=order.quantity
                )
                
                if not can_purchase:
                    stock_issues.append(f"{product.title}: {error_msg}")
                    continue
                
                # Reserve inventory (we don't deduct yet - that happens on payment success)
                calculated_total += (order.price_at_purchase or product.price) * order.quantity
            
            if stock_issues:
                # Unlock cart if there are stock issues
                cart.cart_status = EventCart.CartStatus.ACTIVE
                cart.locked_at = None
                cart.lock_expires_at = None
                cart.save()
                raise serializers.ValidationError({
                    "stock_issues": stock_issues,
                    "message": "Some products are no longer available or exceed purchase limits."
                })
            
            # Keep total in decimal format (pounds)
            calculated_total_decimal = calculated_total
            
            # Validate provided amount if given
            provided_amount = request.data.get('amount')
            if provided_amount is not None:
                if float(provided_amount) != float(calculated_total_decimal):
                    # Unlock cart
                    cart.cart_status = EventCart.CartStatus.ACTIVE
                    cart.locked_at = None
                    cart.lock_expires_at = None
                    cart.save()
                    raise serializers.ValidationError(
                        f"Provided amount (£{provided_amount:.2f}) does not match cart total (£{calculated_total_decimal:.2f})."
                    )
            
            # Create payment record with contact info
            payment = ProductPayment.objects.create(
                user=cart.user,
                cart=cart,
                method=payment_method,
                amount=calculated_total_decimal,
                currency=getattr(cart.event, 'currency', 'gbp'),
                status=ProductPayment.PaymentStatus.PENDING,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone
            )
            
            # Log payment creation
            ProductPaymentLog.log_action(
                payment=payment,
                action='created',
                user=request.user,
                new_status=ProductPayment.PaymentStatus.PENDING,
                notes=f"Payment created for cart {cart.order_reference_id}",
                request=request
            )
            
            # Update cart status
            cart.submitted = True
            cart.active = False
            cart.total = calculated_total  # Ensure total is correctly set
            cart.cart_status = EventCart.CartStatus.LOCKED  # Keep locked until payment completes
            cart.save()
            
            # Create Stripe PaymentIntent if using Stripe
            stripe_client_secret = None
            if payment_method.method == ProductPaymentMethod.MethodType.STRIPE:
                from apps.shop.stripe_service import StripePaymentService
                try:
                    stripe_service = StripePaymentService()
                    
                    # Create PaymentIntent with the payment object
                    payment_intent = stripe_service.create_payment_intent(
                        payment=payment,
                        metadata={
                            'cart_id': str(cart.uuid),
                            'user_email': email,
                            'order_reference': cart.order_reference_id
                        }
                    )
                    
                    # Get client secret for frontend
                    stripe_client_secret = payment_intent['client_secret']
                    
                    payment_status = "Stripe PaymentIntent created - complete payment on frontend"
                    
                    ProductPaymentLog.log_action(
                        payment=payment,
                        action='stripe_intent_created',
                        user=request.user,
                        notes=f"Stripe PaymentIntent created: {payment_intent['id']}",
                        request=request
                    )
                except Exception as e:
                    # Rollback if Stripe fails
                    cart.cart_status = EventCart.CartStatus.ACTIVE
                    cart.submitted = False
                    cart.save()
                    raise serializers.ValidationError(f"Failed to create Stripe payment: {str(e)}")
            else:
                # For non-Stripe payments, they might need manual approval
                payment_status = f"Payment recorded - please follow {payment_method.get_method_display()} instructions"
        
        # Get detailed instructions for bank transfers
        instructions = payment_method.instructions
        if payment_method.method == ProductPaymentMethod.MethodType.BANK_TRANSFER:
            bank_instructions = payment.get_bank_transfer_instructions()
            if bank_instructions:
                instructions = bank_instructions

        # Send order confirmation email in background thread
        def send_email():
            try:
                # send_order_confirmation_email(cart, payment)
                print(f"📧 Order confirmation email queued for order {cart.order_reference_id}")
            except Exception as e:
                print(f"⚠️ Failed to send order confirmation email: {e}")
        
        email_thread = threading.Thread(target=send_email)
        email_thread.start()

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
                "instructions": instructions,
                "lock_expires_at": cart.lock_expires_at.isoformat() if cart.lock_expires_at else None,
                "stripe_client_secret": stripe_client_secret  # Add this for frontend Stripe integration
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
        
        # Check cart status
        if cart.cart_status in [EventCart.CartStatus.LOCKED, EventCart.CartStatus.COMPLETED]:
            raise serializers.ValidationError(f"Cannot modify a {cart.cart_status} cart.")
        
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
        
        # Use transaction for atomicity
        with transaction.atomic():
            # Remove orders not in new list (compare product and size)
            for order in list(cart.orders.all()):
                key = (str(order.product.uuid), order.size.size if order.size else None)
                if key not in new_product_keys:
                    removed_products.append(
                        f"Removed {order.product.title} (size: {order.size.size if order.size else 'N/A'})"
                    )
                    order.delete()

            # Add/update products/orders from new list
            for prod in products:
                product_id = prod.get("id")
                quantity = prod.get("quantity", 1)
                size = prod.get("size", None)

                # Lock product for update
                product_object = EventProduct.objects.select_for_update().get(uuid=product_id)
                
                if product_object.event != cart.event:
                    raise serializers.ValidationError(
                        f"Product {product_object.title} does not belong to the same event as the cart."
                    )
                
                # Check stock
                if product_object.stock < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product_object.title}. Available: {product_object.stock}"
                    )
                
                # Check max purchase per person
                can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                    user=cart.user,
                    product=product_object,
                    quantity=quantity
                )
                
                if not can_purchase:
                    raise serializers.ValidationError(error_msg)

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
                    
                if order:
                    # Update quantity if changed
                    if order.quantity != quantity:
                        order.quantity = quantity
                        order.price_at_purchase = product_object.get_price_for_user(cart.user)
                        order.save()
                        updated_orders.append(
                            f"Updated {product_object.title} (size: {size_object.size if size_object else 'N/A'}, quantity: {quantity})"
                        )
                else:
                    # Create new order only if not found
                    order = EventProductOrder.objects.create(
                        product=product_object,
                        cart=cart,
                        quantity=quantity,
                        size=size_object,
                        price_at_purchase=product_object.get_price_for_user(cart.user)
                    )
                    added_orders.append(
                        f"Added {product_object.title} (size: {size_object.size if size_object else 'N/A'}, quantity: {quantity})"
                    )

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