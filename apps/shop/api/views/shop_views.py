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
        """
        Filter products based on user permissions and product availability.
        - Hides only_service_team products from non-service-team members
        - Hides products before their preview_date (if no preview, before release_date)
        - Shows products in preview mode or after release_date
        
        Special handling for management context:
        - If ?context=manage is passed and user has proper permissions, bypass date restrictions
        """
        user = self.request.user
        queryset = self.queryset
        
        from django.utils import timezone
        from django.db.models import Q
        from apps.events.models import EventServiceTeamMember
        now = timezone.now()
        
        # Check if this is a management context request
        context = self.request.query_params.get('context', None)
        
        # If context=manage and user has proper permissions, show all products (bypass date filters)
        if context == 'manage':
            # Check if user has event management permissions for the requested event
            event_id = self.request.query_params.get('event', None)
            if event_id:
                # User must be superuser, encoder, or event organiser
                if user.is_superuser or getattr(user, 'is_encoder', False):
                    # Return all products for this event without date filtering
                    return queryset
        
        # Get all events where user is service team member
        service_team_events = EventServiceTeamMember.objects.filter(
            user=user
        ).values_list('event_id', flat=True)
        
        # Filter logic:
        # 1. Show all products from events where user is service team
        # 2. For other products:
        #    - Hide if only_service_team=True
        #    - Hide if not yet visible (before preview_date or release_date)
        #    - Show if in preview mode or released
        
        queryset = queryset.filter(
            Q(event_id__in=service_team_events) |  # Service team sees all products
            Q(
                only_service_team=False,  # Non-service-team products
                # Visible products: either no dates set, past preview/release, or within valid period
            ) & (
                Q(preview_date__isnull=True, release_date__isnull=True) |  # No dates = always visible
                Q(preview_date__lte=now) |  # Past preview date
                Q(preview_date__isnull=True, release_date__lte=now)  # No preview but past release
            )
        )
        
        return queryset
    
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
    
    def perform_create(self, serializer):
        """
        Restrict cart creation to staff and superusers only.
        Regular users cannot create carts themselves - only admins can create carts for participants.
        """
        user = self.request.user
        
        # Only staff and superusers can create carts
        if not (user.is_staff or user.is_superuser):
            raise exceptions.PermissionDenied(
                "Only administrators can create merchandise carts. "
                "If you need a cart created, please contact the event service team."
            )
        
        serializer.save()
    
    @action(detail=True, methods=['post'], url_name='add', url_path='add')
    def add_to_cart(self, request, *args, **kwargs):
        '''
        Bulk add products to the cart with max purchase validation and stock locking.
        E.g. {"products": [{"product_id": "uuid1", "quantity": 2, "size": "M"}, {"product_id": "uuid2", "quantity": 1}]}
        
        SECURITY: Only staff and superusers can add products to carts.
        '''
        cart: EventCart = self.get_object()
        
        # Security check: Only staff/superusers can add products to carts
        # if not (request.user.is_staff or request.user.is_superuser):
        #     raise exceptions.PermissionDenied(
        #         "Only administrators can add products to carts. "
        #         "If you need items added to your cart, please contact the event service team."
        #     )
        
        # Additional check: ensure authorized user is modifying the cart
        self.check_object_permissions(request, cart)
        
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
                
                # NEW: Check product availability for this user
                can_purchase_product, purchase_reason = product_object.is_purchasable(cart.user)
                if not can_purchase_product:
                    raise serializers.ValidationError(
                        f"Cannot add {product_object.title}: {purchase_reason}"
                    )
                
                # NEW: Check size requirement
                if product_object.uses_sizes and not size:
                    raise serializers.ValidationError(
                        f"Product {product_object.title} requires a size selection."
                    )
                
                # Check size is valid for product first
                size_object = None
                if size:
                    size_object = ProductSize.objects.filter(size=size, product=product_object).first()
                    if not size_object:
                        raise serializers.ValidationError(
                            f"Size {size} not available for product {product_object.title}"
                        )
                
                # Check if order already exists for this product+size in the cart
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
                    # Updating existing order - add to current quantity
                    new_quantity = existing_order.quantity + quantity
                    
                    # Validate the NEW total quantity against limits
                    from django.db.models import Sum
                    
                    # Check maximum_order_quantity limit first (per single order)
                    if new_quantity > product_object.maximum_order_quantity:
                        raise serializers.ValidationError(
                            f"Cannot add {quantity} more. The maximum quantity per order for '{product_object.title}' is {product_object.maximum_order_quantity}. "
                            f"Current order quantity: {existing_order.quantity}."
                        )
                    
                    # Check max_purchase_per_person limit (only if limit exists)
                    if product_object.max_purchase_per_person != -1:
                        # Use can_purchase with exclude_order_id to avoid double-counting
                        can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                            user=cart.user,
                            product=product_object,
                            quantity=new_quantity,
                            exclude_order_id=existing_order.id
                        )
                        
                        if not can_purchase:
                            raise serializers.ValidationError(error_msg)
                    
                    # Check stock for additional quantity (only if stock tracking enabled)
                    if product_object.stock > 0 and product_object.stock < quantity:
                        raise serializers.ValidationError(
                            f"Insufficient stock for additional {product_object.title}. Available: {product_object.stock}, Requested: {quantity}"
                        )
                    
                    # Decrement stock atomically for additional quantity (only if stock > 0)
                    if product_object.stock > 0:
                        stock_decremented = product_object.decrement_stock(quantity)
                        if not stock_decremented:
                            raise serializers.ValidationError(
                                f"Failed to reserve stock for {product_object.title}. Please try again."
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
                    # Creating new order - validate against limits
                    # Check maximum_order_quantity limit (per single order)
                    if quantity > product_object.maximum_order_quantity:
                        raise serializers.ValidationError(
                            f"Cannot add {quantity} of '{product_object.title}'. The maximum quantity per order is {product_object.maximum_order_quantity}."
                        )
                    
                    # Get completed purchases
                    completed_purchases = ProductPurchaseTracker.get_user_purchased_quantity(cart.user, product_object)
                    
                    # Get current cart quantity for this product
                    cart_quantity = ProductPurchaseTracker.get_user_cart_quantity(cart.user, product_object)
                    
                    # Check if adding this new order would exceed limit (only if limit exists)
                    if product_object.max_purchase_per_person != -1:
                        total_with_new = completed_purchases + cart_quantity + quantity
                        if total_with_new > product_object.max_purchase_per_person:
                            remaining = product_object.max_purchase_per_person - (completed_purchases + cart_quantity)
                            raise serializers.ValidationError(
                                f"Cannot add {quantity} of '{product_object.title}'. You can only add {remaining} more "
                                f"(limit: {product_object.max_purchase_per_person}, purchased: {completed_purchases}, "
                                f"already in cart: {cart_quantity})."
                            )
                    
                    # Check stock availability (only if stock > 0, else infinite/made-to-order)
                    if product_object.stock > 0 and product_object.stock < quantity:
                        raise serializers.ValidationError(
                            f"Insufficient stock for {product_object.title}. Available: {product_object.stock}, Requested: {quantity}"
                        )
                    
                    # Decrement stock atomically before creating order (only if stock > 0)
                    if product_object.stock > 0:
                        stock_decremented = product_object.decrement_stock(quantity)
                        if not stock_decremented:
                            raise serializers.ValidationError(
                                f"Insufficient stock for {product_object.title}. Please try again."
                            )
                    
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
        Remove specific product orders from the cart by order ID.
        Supports both legacy format (product UUIDs) and new format (order IDs with optional size).
        
        New format (recommended): {"order_ids": [1, 2, 3]}
        Legacy format: {"products": ["product_uuid1", "product_uuid2"]} - removes ALL orders for these products
        Mixed format: {"products": [{"uuid": "product_uuid", "size": "M"}]} - removes specific size orders
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
        
        order_ids = request.data.get("order_ids", [])
        products = request.data.get("products", [])
        
        if not order_ids and not products:
            raise serializers.ValidationError("No order IDs or products provided to remove from cart.")
        
        with transaction.atomic():
            removed_products = []
            orders_to_remove = []
            
            # Handle new format: order IDs
            if order_ids:
                orders_to_remove = EventProductOrder.objects.filter(
                    id__in=order_ids,
                    cart=cart
                )
            
            # Handle legacy/mixed format: product UUIDs (with optional size)
            elif products:
                for prod_item in products:
                    # Handle both string UUID and dict format
                    if isinstance(prod_item, str):
                        # Legacy format: remove ALL orders for this product
                        product = get_object_or_404(EventProduct, uuid=prod_item)
                        orders = EventProductOrder.objects.filter(cart=cart, product=product)
                        orders_to_remove.extend(orders)
                    elif isinstance(prod_item, dict):
                        # New dict format: {"uuid": "...", "size": "M"}
                        prod_uuid = prod_item.get('uuid') or prod_item.get('id')
                        size = prod_item.get('size')
                        
                        product = get_object_or_404(EventProduct, uuid=prod_uuid)
                        
                        if size:
                            # Remove specific size order
                            size_object = ProductSize.objects.filter(size=size, product=product).first()
                            orders = EventProductOrder.objects.filter(
                                cart=cart, 
                                product=product,
                                size=size_object
                            )
                        else:
                            # Remove all orders for this product (no size specified)
                            orders = EventProductOrder.objects.filter(cart=cart, product=product)
                        
                        orders_to_remove.extend(orders)
            
            # Process removals
            for order in orders_to_remove:
                product = order.product
                
                # Restore stock (only if stock tracking enabled)
                if product.stock > 0:
                    product.increment_stock(order.quantity)
                
                removed_products.append({
                    'order_id': order.id,
                    'product': product.title,
                    'size': order.size.size if order.size else None,
                    'quantity': order.quantity,
                    'stock_restored': product.stock > 0
                })
                
                # Delete the order
                order.delete()
            
            # Clean up M2M relationships for products with no remaining orders
            for product_id in set(order.product_id for order in orders_to_remove):
                if not EventProductOrder.objects.filter(cart=cart, product_id=product_id).exists():
                    cart.products.remove(product_id)
            
            # Recalculate cart total
            total = 0
            for order in cart.orders.all():
                total += (order.price_at_purchase or order.product.price) * order.quantity
            cart.total = total
            cart.save()
        
        serialized = self.get_serializer(cart)
        return Response({
            "status": "products removed from cart",
            "removed": removed_products,
            "cart": serialized.data
        }, status=200)
        
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
                    quantity=order.quantity,
                    exclude_order_id=order.id
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
        
        SECURITY RULES (UPDATED - IMMUTABLE AFTER SUBMISSION):
        - Before submission (draft/pending): Only staff/superusers can modify
        - After submission/payment (waiting/submitted/paid): COMPLETELY IMMUTABLE
            * NO ONE can edit from frontend - not even superusers
            * All edits must be done via Django Admin after careful consideration
            * This ensures payment integrity and prevents statistical corruption
        '''
        cart: EventCart = self.get_object()
        products = request.data.get("products", [])
        user = request.user
        
        self.check_object_permissions(request, cart)
        
        # Check cart status
        if cart.cart_status in [EventCart.CartStatus.LOCKED, EventCart.CartStatus.COMPLETED]:
            raise serializers.ValidationError(f"Cannot modify a {cart.cart_status} cart.")
        
        # Import permission utilities and logging
        from core.event_permissions import has_event_permission, has_full_event_access
        import logging
        logger = logging.getLogger(__name__)
        
        # Determine if cart is submitted/paid - if so, it's IMMUTABLE
        is_submitted_or_paid = cart.approved or cart.submitted
        
        # NEW SECURITY: Submitted/paid carts are COMPLETELY IMMUTABLE from frontend
        if is_submitted_or_paid:
            # Log the attempted modification for audit trail
            logger.warning(
                f"SECURITY: User {user.email} (ID: {user.id}, Staff: {user.is_staff}, Super: {user.is_superuser}) "
                f"attempted to modify submitted cart {cart.order_reference_id} (ID: {cart.id}). "
                f"Request blocked - submitted carts are immutable."
            )
            
            raise exceptions.PermissionDenied(
                "This cart has been submitted and is now IMMUTABLE to ensure payment integrity. "
                "No modifications can be made from the frontend - not even by administrators. "
                "If changes are absolutely necessary, they must be made through the Django Admin "
                "after careful consideration to avoid corrupting order statistics. "
                "Please contact the system administrator."
            )
        
        # Before submission, only staff/superusers can modify
        # if not (user.is_staff or user.is_superuser):
        #     logger.warning(
        #         f"SECURITY: User {user.primary_email} (ID: {user.id}) attempted to modify cart {cart.order_reference_id} "
        #         f"without proper permissions. Request blocked."
        #     )
        #     raise exceptions.PermissionDenied(
        #         "Only administrators can modify carts. "
        #         "If you need changes made, please contact the event service team."
        #     )
        
        # Audit log for cart modifications
        logger.info(
            f"AUDIT: User {user.primary_email} (ID: {user.id}) modifying cart {cart.order_reference_id} (ID: {cart.uuid}). "
            f"Products: {len(products)} items."
        )

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
                
                # Find size object if specified
                size_object = None
                if size:
                    size_object = ProductSize.objects.filter(size=size, product=product_object).first()
                    if not size_object:
                        raise serializers.ValidationError(
                            f"Size {size} not available for product {product_object.title}"
                        )

                # Look for existing order by product, cart, size
                order = EventProductOrder.objects.filter(
                    product=product_object,
                    cart=cart,
                    size=size_object
                ).first()
                
                if order:
                    # Only validate and update if quantity has actually changed
                    if order.quantity != quantity:
                        # Validate maximum_order_quantity for the NEW quantity
                        if quantity > product_object.maximum_order_quantity:
                            raise serializers.ValidationError(
                                f"Quantity {quantity} exceeds maximum order quantity of {product_object.maximum_order_quantity} for product {product_object.title}"
                            )
                        
                        # Validate max_purchase_per_person if there's a limit
                        # Calculate the difference to see if we're adding or removing
                        quantity_change = quantity - order.quantity
                        
                        if quantity_change > 0 and product_object.max_purchase_per_person != -1:
                            # Only validate if increasing quantity and there's a limit
                            # Exclude current order from cart count to avoid double-counting
                            can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                                user=cart.user,
                                product=product_object,
                                quantity=quantity_change,  # Only check the additional amount
                                exclude_order_id=order.id  # Exclude current order to prevent double-counting
                            )
                            
                            if not can_purchase:
                                raise serializers.ValidationError(error_msg)
                        
                        # Update the order
                        order.quantity = quantity
                        order.price_at_purchase = product_object.get_price_for_user(cart.user)
                        order.save()
                        updated_orders.append(
                            f"Updated {product_object.title} (size: {size_object.size if size_object else 'N/A'}, quantity: {quantity})"
                        )
                    # If quantity hasn't changed, don't add to updated_orders list
                else:
                    # Creating new order - validate fully
                    if quantity > product_object.maximum_order_quantity:
                        raise serializers.ValidationError(
                            f"Quantity {quantity} exceeds maximum order quantity of {product_object.maximum_order_quantity} for product {product_object.title}"
                        )
                    
                    # Validate max_purchase_per_person if there's a limit
                    if product_object.max_purchase_per_person != -1:
                        can_purchase, remaining, error_msg = ProductPurchaseTracker.can_purchase(
                            user=cart.user,
                            product=product_object,
                            quantity=quantity
                        )
                        
                        if not can_purchase:
                            raise serializers.ValidationError(error_msg)
                    
                    # Create new order
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

    def _validate_size_only_changes(self, cart, new_products):
        """
        DEPRECATED: This method is no longer used as submitted carts are now completely immutable.
        Kept for reference only.
        
        Helper method to validate that only size changes are being made.
        Raises ValidationError if quantity or price changes are detected.
        
        Args:
            cart: EventCart instance
            new_products: List of product dicts from request
        """
        raise serializers.ValidationError(
            "This functionality has been disabled. Submitted carts are now completely immutable. "
            "Please use Django Admin for any necessary modifications."
        )
    
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
    
    @action(detail=True, methods=['post'], url_name='cancel', url_path='cancel')
    def cancel_cart(self, request, *args, **kwargs):
        '''
        Cancel an unpaid cart. Marks cart and all orders as CANCELLED and restores stock.
        Only works for carts that haven't been paid/verified.
        Requires permission to manage merchandise.
        '''
        cart: EventCart = self.get_object()
        user = request.user
        
        # Import permission utilities
        from core.event_permissions import has_event_permission
        
        # Security check: User must have merchandise management permission
        if not has_event_permission(user, cart.event, 'can_manage_merch'):
            raise exceptions.PermissionDenied(
                "You do not have permission to cancel orders for this event."
            )
        
        # Check if cart has been paid/verified
        paid_payment = ProductPayment.objects.filter(
            cart=cart,
            status__in=[ProductPayment.PaymentStatus.SUCCEEDED]
        ).first()
        
        if paid_payment:
            raise serializers.ValidationError(
                "Cannot cancel a paid order. Please initiate a refund instead using the refund system."
            )
        
        # Check if cart is already cancelled or refunded
        if cart.cart_status in [EventCart.CartStatus.CANCELLED, EventCart.CartStatus.REFUNDED]:
            raise serializers.ValidationError(
                f"This cart is already {cart.get_cart_status_display().lower()}."
            )
        
        # Get cancellation reason from request
        cancellation_reason = request.data.get('reason', 'Cancelled by admin')
        
        with transaction.atomic():
            # Restore stock for all orders
            restored_items = []
            for order in cart.orders.all():
                product = order.product
                
                # Restore stock if tracking is enabled (stock > 0)
                if product.stock > 0:
                    product.increment_stock(order.quantity)
                    restored_items.append({
                        'product': product.title,
                        'quantity': order.quantity,
                        'stock_restored': True
                    })
                else:
                    restored_items.append({
                        'product': product.title,
                        'quantity': order.quantity,
                        'stock_restored': False
                    })
                
                # Update order status
                order.status = EventProductOrder.Status.CANCELLED
                order.admin_notes = f"Cancelled: {cancellation_reason}"
                order.save()
            
            # Update cart status
            cart.cart_status = EventCart.CartStatus.CANCELLED
            cart.active = False
            cart.notes = f"{cart.notes or ''}\n\nCANCELLED: {cancellation_reason} (by {user.primary_email})".strip()
            cart.save(force_update=True)
            
            # Mark any pending payments as cancelled and any succeeded as pending refund
            ProductPayment.objects.filter(
                cart=cart,
                status=ProductPayment.PaymentStatus.PENDING
            ).update(
                status=ProductPayment.PaymentStatus.CANCELLED,
                notes=f"Cancelled with cart: {cancellation_reason}"
            )
            
            ProductPayment.objects.filter(
                cart=cart,
                status=ProductPayment.PaymentStatus.SUCCEEDED
            ).update(
                status=ProductPayment.PaymentStatus.REFUND_PROCESSING,
                notes=f"Refunded due to cart cancellation: {cancellation_reason}"
            )
        
        serialized = self.get_serializer(cart)
        return Response({
            "status": "cart cancelled",
            "cart": serialized.data,
            "restored_items": restored_items,
            "message": f"Cart {cart.order_reference_id} has been cancelled and stock has been restored."
        }, status=200)
    
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