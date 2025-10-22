from rest_framework import serializers
from apps.shop.models.payments import ProductPaymentMethod, ProductPaymentPackage, ProductPayment
from apps.shop.models.shop_models import EventProduct, EventCart

class ProductPaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for ProductPaymentMethod with security validations."""
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    
    class Meta:
        model = ProductPaymentMethod
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "method_display"]
        
    def validate(self, attrs):
        """Validate payment method data for security."""
        # Ensure sensitive payment details are properly handled
        method = attrs.get('method')
        
        if method == ProductPaymentMethod.MethodType.BANK_TRANSFER:
            required_fields = ['account_name', 'account_number']
            for field in required_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        f"{field.replace('_', ' ').title()} is required for bank transfer payments."
                    )
        
        return attrs

class ProductPaymentPackageSerializer(serializers.ModelSerializer):
    """
    Serializer for ProductPaymentPackage model with nested product creation.
    
    Example API object:
    {
        "name": "Merchandise Bundle",
        "description": "T-shirt, hoodie, and conference bag combo",
        "price": 75.00,  // Price in pounds (£75.00)
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "currency": "gbp",
        "products": ["789e0123-e89b-12d3-a456-426614174002", "012e3456-e89b-12d3-a456-426614174003"],
        "available_from": "2025-01-01T00:00:00Z",
        "available_until": "2025-12-31T23:59:59Z",
        "is_active": true,
        "product_data": [
            {
                "title": "Conference Mug",
                "description": "Ceramic mug with conference logo",
                "price": 12.50,
                "category": "accessories",
                "stock": 100
            }
        ]
    }
    
    Response includes additional computed fields:
    {
        "id": 1,
        "price_display": "75.00 GBP",
        "created_at": "2025-01-15T09:00:00Z",
        "updated_at": "2025-01-15T09:00:00Z"
    }
    """
    products = serializers.PrimaryKeyRelatedField(many=True, queryset=EventProduct.objects.all(), required=False)
    price_display = serializers.SerializerMethodField()
    
    # Write-only fields for creating products
    product_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of product dicts to create and associate with this package"
    )

    class Meta:
        model = ProductPaymentPackage
        fields = [
            "id", "name", "description", "price", "price_display", "event", "currency", 
            "products", "product_data", "available_from", "available_until", 
            "is_active", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "price_display", "created_at", "updated_at"]
        
    def get_price_display(self, obj):
        return f"{obj.price:.2f} {obj.currency.upper()}"
    
    def create(self, validated_data):
        from apps.shop.models.shop_models import EventProduct
        product_data = validated_data.pop('product_data', [])
        products = validated_data.pop('products', [])
        
        # Create the package
        package = super().create(validated_data)
        
        # Associate existing products
        if products:
            package.products.set(products)
        
        # Create and associate new products
        for product_dict in product_data:
            product = EventProduct.objects.create(
                title=product_dict.get('title', ''),
                description=product_dict.get('description', ''),
                price=product_dict.get('price', 0),
                event=package.event,
                seller=self.context['request'].user if 'request' in self.context else None,
                category=product_dict.get('category', 'other'),
                stock=product_dict.get('stock', 0)
            )
            package.products.add(product)
        
        return package
    
    def update(self, instance, validated_data):
        from apps.shop.models.shop_models import EventProduct
        product_data = validated_data.pop('product_data', None)
        products = validated_data.pop('products', None)
        
        # Update the package
        package = super().update(instance, validated_data)
        
        # Handle product associations
        if products is not None:
            package.products.set(products)
        
        # Create and associate new products (don't remove existing)
        if product_data is not None:
            for product_dict in product_data:
                product = EventProduct.objects.create(
                    title=product_dict.get('title', ''),
                    description=product_dict.get('description', ''),
                    price=product_dict.get('price', 0),
                    event=package.event,
                    seller=self.context['request'].user if 'request' in self.context else None,
                    category=product_dict.get('category', 'other'),
                    stock=product_dict.get('stock', 0)
                )
                package.products.add(product)
        
        return package

class ProductPaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for ProductPayment model with cart and package relationships.
    
    Example API object:
    {
        "user": 1,  // User ID
        "cart": "345e6789-e89b-12d3-a456-426614174004",  // EventCart UUID
        "package": 2,  // ProductPaymentPackage ID (optional)
        "method": 1,   // ProductPaymentMethod ID
        "amount": 125.50,  // Amount in pounds (£125.50)
        "currency": "gbp",
        "status": "PENDING",
        "stripe_payment_intent": "pi_9876543210",
        "approved": false
    }
    
    Response includes additional computed fields:
    {
        "id": 1,
        "payment_reference_id": "PAY3456789012-0000000001",
        "user_email": "user@example.com",  // user.primary_email
        "cart_id": "345e6789-e89b-12d3-a456-426614174004",
        "package_name": "Merchandise Bundle",
        "method_display": "Stripe",
        "amount_display": "125.50 GBP",
        "status_display": "Pending",
        "paid_at": null,
        "created_at": "2025-01-15T10:40:00Z",
        "updated_at": "2025-01-15T10:40:00Z"
    }
    """
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    cart_id = serializers.CharField(source="cart.uuid", read_only=True)
    method_display = serializers.CharField(source="method.get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = ProductPayment
        fields = [
            "id", "payment_reference_id", "bank_reference", "user", "user_email", "cart", "cart_id", 
            "package", "package_name", "method", "method_display", "stripe_payment_intent", 
            "amount", "amount_display", "currency", "status", "status_display", 
            "approved", "paid_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "payment_reference_id", "bank_reference", "user_email", "cart_id", 
                           "method_display", "status_display", "package_name", "amount_display", 
                           "created_at", "updated_at"]
                           
    def get_amount_display(self, obj):
        return f"{obj.amount:.2f} {obj.currency.upper()}"
    
    def validate_amount(self, value):
        """Validate payment amount is positive and reasonable."""
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be positive.")
        if value > 1000000:  # £1,000,000 in pounds
            raise serializers.ValidationError("Payment amount exceeds maximum allowed.")
        return value
    
    def validate(self, attrs):
        """Validate payment data for security and consistency."""
        cart = attrs.get('cart')
        method = attrs.get('method')
        amount = attrs.get('amount')
        
        # If cart is provided, validate method is available for the cart's event
        if cart and method:
            if method.event and method.event != cart.event:
                raise serializers.ValidationError(
                    "Payment method is not available for this cart's event."
                )
            
            # Validate amount matches cart total (within reason)
            if amount and cart.total:
                cart_total_decimal = cart.total
                if abs(amount - cart_total_decimal) > 0.01:  # Allow 1 penny difference for rounding
                    raise serializers.ValidationError(
                        f"Payment amount (£{amount:.2f}) does not match cart total (£{cart_total_decimal:.2f})."
                    )
        
        return super().validate(attrs)
    
    def create(self, validated_data):
        # Set user from request context if not provided
        if not validated_data.get('user') and 'request' in self.context:
            validated_data['user'] = self.context['request'].user
        
        # Ensure cart belongs to the user (security check)
        cart = validated_data.get('cart')
        user = validated_data.get('user')
        if cart and user and cart.user != user:
            request_user = self.context.get('request', {}).user if 'request' in self.context else None
            if not (request_user and (request_user.is_superuser or getattr(request_user, 'is_encoder', False))):
                raise serializers.ValidationError("Cannot create payment for another user's cart.")
            
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Security check: only allow certain status changes
        request_user = self.context.get('request', {}).user if 'request' in self.context else None
        
        if 'status' in validated_data:
            # Only admins can manually change payment status
            if not (request_user and (request_user.is_superuser or getattr(request_user, 'is_encoder', False))):
                # Regular users can only cancel pending payments
                if instance.status != ProductPayment.PaymentStatus.PENDING or validated_data['status'] != ProductPayment.PaymentStatus.FAILED:
                    raise serializers.ValidationError("You don't have permission to change this payment status.")
        
        # Handle status changes and approval
        if 'status' in validated_data and validated_data['status'] == ProductPayment.PaymentStatus.SUCCEEDED:
            if not instance.paid_at:
                instance.mark_as_paid()
            validated_data['approved'] = True
        
        return super().update(instance, validated_data)


class ProductPaymentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing product payments in participant management views.
    Optimized for minimal data transfer with essential payment, cart, and user info.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    user_member_id = serializers.CharField(source="user.member_id", read_only=True)
    user_area = serializers.SerializerMethodField()
    user_chapter = serializers.SerializerMethodField()
    
    cart_order_reference = serializers.CharField(source="cart.order_reference_id", read_only=True)
    cart_total = serializers.DecimalField(source="cart.total", max_digits=10, decimal_places=2, read_only=True)
    cart_product_count = serializers.SerializerMethodField()
    
    payment_method = serializers.CharField(source="method.get_method_display", read_only=True)
    payment_method_type = serializers.CharField(source="method.method", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()
    
    # Participant info (if user is a participant in the event)
    participant_event_pax_id = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductPayment
        fields = [
            "id", "user_id", "user_name", "user_email", "user_member_id",
            "user_area", "user_chapter", "participant_event_pax_id",
            "payment_reference_id", "bank_reference",
            "cart_order_reference", "cart_total", "cart_product_count",
            "payment_method", "payment_method_type", "package_name",
            "amount", "amount_display", "currency",
            "status", "status_display", "approved",
            "paid_at", "created_at"
        ]
    
    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}"
        return "Unknown"
    
    def get_user_area(self, obj):
        if obj.user and hasattr(obj.user, 'area_from') and obj.user.area_from:
            return obj.user.area_from.area_name
        return None
    
    def get_user_chapter(self, obj):
        if obj.user and hasattr(obj.user, 'area_from') and obj.user.area_from:
            area = obj.user.area_from
            if hasattr(area, 'unit') and area.unit and hasattr(area.unit, 'chapter') and area.unit.chapter:
                return area.unit.chapter.chapter_name
        return None
    
    def get_amount_display(self, obj):
        return f"£{obj.amount:.2f}"
    
    def get_cart_product_count(self, obj):
        if obj.cart:
            return obj.cart.orders.count()
        return 0
    
    def get_participant_event_pax_id(self, obj):
        """Get the participant's event_pax_id if they're registered for the cart's event"""
        if obj.cart and obj.cart.event and obj.user:
            from apps.events.models import EventParticipant
            participant = EventParticipant.objects.filter(
                event=obj.cart.event,
                user=obj.user
            ).first()
            if participant:
                return participant.event_pax_id
        return None