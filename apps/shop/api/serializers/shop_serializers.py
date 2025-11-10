from rest_framework import serializers
from apps.shop.api.serializers.shop_metadata_serializers import (
    ProductImageSerializer, ProductCategorySerializer, ProductMaterialSerializer, ProductSizeSerializer
)
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder

class EventProductSerializer(serializers.ModelSerializer):
    """
    Serializer for EventProduct model with comprehensive product management.
    
    Example API object:
    {
        "title": "Conference T-Shirt",
        "description": "Official conference t-shirt with logo",
        "extra_info": "Made from 100% organic cotton",
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "price": 25.00,
        "discount": 2.50,
        "seller": 1,  // CommunityUser ID (will use seller.primary_email)
        "category": "clothing",
        "stock": 100,
        "featured": true,
        "colors": ["red", "blue", "white"],
        "maximum_order_quantity": 5,
        "image_uploads": [/* image files */],
        "size_list": "[\"S\", \"M\", \"L\", \"XL\"]",  // JSON string
        "category_ids": "[1, 2]",  // JSON string of category IDs
        "material_ids": "[1]"      // JSON string of material IDs
    }
    
    Response includes additional computed fields:
    {
        "uuid": "789e0123-e89b-12d3-a456-426614174002",
        "seller_email": "seller@example.com",  // seller.primary_email
        "event_name": "Anchored Conference 2025",
        "imageUrl": "https://example.com/media/product.jpg",
        "sizes": ["S", "M", "L", "XL"],
        "in_stock": true,
        "categories": [...],  // ProductCategorySerializer data
        "materials": [...],   // ProductMaterialSerializer data
        "images": [...],      // ProductImageSerializer data
        "product_sizes": [...]  // ProductSizeSerializer data
    }
    """
    seller_email = serializers.EmailField(source="seller.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    
    # Related model serializers
    categories = ProductCategorySerializer(many=True, read_only=True)  
    materials = ProductMaterialSerializer(many=True, read_only=True) 
    images = ProductImageSerializer(many=True, read_only=True)  # Multiple images
    product_sizes = ProductSizeSerializer(many=True, read_only=True)
    
    # Frontend compatibility fields
    imageUrl = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    user_purchased_count = serializers.SerializerMethodField()
    
    # Write-only fields for creating/updating
    image_uploads = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        help_text="Upload multiple product images"
    )
    size_list = serializers.CharField(
        write_only=True,
        required=False,
        help_text="JSON string of sizes to create for this product"
    )
    category_ids = serializers.CharField(
        write_only=True,
        required=False,
        help_text="JSON string of category IDs to associate with this product"
    )
    material_ids = serializers.CharField(
        write_only=True,
        required=False,
        help_text="JSON string of material IDs to associate with this product"
    )
    
    def get_imageUrl(self, obj):
        """Get the primary image URL"""
        url = obj.primary_image_url
        
        if url and not url.startswith('http'):
            from django.conf import settings
            # Check if URL already starts with media path to avoid duplication
            if url.startswith('/media/') or url.startswith('media/'):
                return url if url.startswith('/') else f"/{url}"
            # Make URL absolute if it's relative
            absolute_url = f"{settings.MEDIA_URL}{url.lstrip('/')}"
            return absolute_url
        return url
    
    def get_sizes(self, obj):
        """Get list of available sizes"""
        return obj.available_sizes
    
    def get_user_purchased_count(self, obj):
        """Get the count of how many of this product the requesting user has purchased"""
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return 0
        
        from apps.shop.models.shop_models import ProductPurchaseTracker
        try:
            tracker = ProductPurchaseTracker.objects.get(user=request.user, product=obj)
            return tracker.total_purchased
        except ProductPurchaseTracker.DoesNotExist:
            return 0
    
    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "description", "extra_info", "event", "event_name",
            "price", "discount", "seller", "seller_email", "category", "stock", "featured", 
            "in_stock", "imageUrl", "sizes", "colors",
            "categories", "materials", "images", "product_sizes", "maximum_order_quantity",
            "max_purchase_per_person",  # New field for purchase limits
            "user_purchased_count",  # New field for frontend validation
            "image_uploads", "size_list", "category_ids", "material_ids"
        ]
        read_only_fields = ["seller", "seller_email", "uuid", "event_name", "in_stock", "imageUrl", "sizes", "user_purchased_count"]
        
    def create(self, validated_data):
        # Extract related data
        import json
        image_uploads = validated_data.pop('image_uploads', [])
        size_list_raw = validated_data.pop('size_list', '')
        category_ids_raw = validated_data.pop('category_ids', '')
        material_ids_raw = validated_data.pop('material_ids', '')
        
        # Parse JSON strings
        size_list = []
        if size_list_raw:
            try:
                size_list = json.loads(size_list_raw)
            except json.JSONDecodeError:
                size_list = [size_list_raw] if size_list_raw else []
                
        category_ids = []
        if category_ids_raw:
            try:
                category_ids = json.loads(category_ids_raw)
            except json.JSONDecodeError:
                # Try to parse as single integer
                try:
                    category_ids = [int(category_ids_raw)]
                except ValueError:
                    category_ids = []
                
        material_ids = []
        if material_ids_raw:
            try:
                material_ids = json.loads(material_ids_raw)
            except json.JSONDecodeError:
                # Try to parse as single integer
                try:
                    material_ids = [int(material_ids_raw)]
                except ValueError:
                    material_ids = []
        
        # print(f"DEBUG - Creating product with:")
        # print(f"  - Images: {len(image_uploads)} files")
        # print(f"  - Sizes: {size_list} (parsed from {size_list_raw})")
        # print(f"  - Categories: {category_ids} (parsed from {category_ids_raw})")
        # print(f"  - Materials: {material_ids} (parsed from {material_ids_raw})")
        # print(f"  - Colors: {validated_data.get('colors', [])}")
        
        # Ensure colors is a list and parse if it's a JSON string
        colors = validated_data.get('colors', [])
        if isinstance(colors, str):
            try:
                colors = json.loads(colors)
            except json.JSONDecodeError:
                colors = [colors] if colors else []
        elif colors is None:
            colors = []
        validated_data['colors'] = colors
            
        # Create the product
        product = super().create(validated_data)
        
        # Handle images
        from apps.shop.models.metadata_models import ProductImage
        for image_file in image_uploads:
            ProductImage.objects.create(product=product, image=image_file)
        
        # Handle sizes with proper mapping
        from apps.shop.models.metadata_models import ProductSize
        size_mapping = {
            # Backend enum values (exact matches)
            'XS': ProductSize.Sizes.EXTRA_SMALL,
            'SM': ProductSize.Sizes.SMALL,
            'MD': ProductSize.Sizes.MEDIUM,
            'LG': ProductSize.Sizes.LARGE,
            'XL': ProductSize.Sizes.EXTRA_LARGE,
            # Common frontend abbreviations (for compatibility)
            'EXTRA_SMALL': ProductSize.Sizes.EXTRA_SMALL,
            'S': ProductSize.Sizes.SMALL,
            'SMALL': ProductSize.Sizes.SMALL,
            'M': ProductSize.Sizes.MEDIUM,
            'MEDIUM': ProductSize.Sizes.MEDIUM,
            'L': ProductSize.Sizes.LARGE,
            'LARGE': ProductSize.Sizes.LARGE,
            'XXL': ProductSize.Sizes.EXTRA_LARGE,
            'EXTRA_LARGE': ProductSize.Sizes.EXTRA_LARGE,
        }
        
        for size_name in size_list:
            size_key = size_name.strip().upper().replace(' ', '_')
            
            # Handle special cases
            if size_key in ['ONE_SIZE', 'ONESIZE', 'ONE SIZE']:
                # For "One Size", use Medium as default
                ProductSize.objects.create(product=product, size=ProductSize.Sizes.MEDIUM)
                print(f"DEBUG - Created One Size as MEDIUM")
            elif size_key in size_mapping:
                ProductSize.objects.create(product=product, size=size_mapping[size_key])
                print(f"DEBUG - Created size: {size_mapping[size_key]}")
            else:
                # Default fallback
                ProductSize.objects.create(product=product, size=ProductSize.Sizes.MEDIUM)
                print(f"DEBUG - Created fallback size: MEDIUM for '{size_name}'")
        
        # Handle categories and materials
        if category_ids:
            product.categories.set(category_ids)
        if material_ids:
            product.materials.set(material_ids)
        
        # print(f"DEBUG - Product created with:")
        # print(f"  - {product.images.count()} images")
        # print(f"  - {product.product_sizes.count()} sizes")
        # print(f"  - {product.categories.count()} categories")
        # print(f"  - {product.materials.count()} materials")
        # print(f"  - Colors: {product.colors}")
        # print(f"  - Product sizes: {[s.size for s in product.product_sizes.all()]}")
            
        return product
    
    def update(self, instance, validated_data):
        # Extract related data
        import json
        # print(f"DEBUG UPDATE - Instance: {instance.title} (ID: {instance.uuid})")
        # print(f"DEBUG UPDATE - Validated data keys: {list(validated_data.keys())}")
        # print(f"DEBUG UPDATE - Validated data: {validated_data}")

        image_uploads = validated_data.pop('image_uploads', None)
        size_list_raw = validated_data.pop('size_list', None)
        category_ids_raw = validated_data.pop('category_ids', None)
        material_ids_raw = validated_data.pop('material_ids', None)

        # print(f"DEBUG UPDATE - Extracted data: images={len(image_uploads) if image_uploads else 0}, sizes={size_list_raw}, categories={category_ids_raw}, materials={material_ids_raw}")

        # Parse JSON strings
        size_list = None
        if size_list_raw is not None:
            try:
                size_list = json.loads(size_list_raw)
            except json.JSONDecodeError:
                size_list = [size_list_raw] if size_list_raw else []
                
        category_ids = None
        if category_ids_raw is not None:
            try:
                category_ids = json.loads(category_ids_raw)
            except json.JSONDecodeError:
                # Try to parse as single integer
                try:
                    category_ids = [int(category_ids_raw)]
                except ValueError:
                    category_ids = []
                
        material_ids = None
        if material_ids_raw is not None:
            try:
                material_ids = json.loads(material_ids_raw)
            except json.JSONDecodeError:
                # Try to parse as single integer
                try:
                    material_ids = [int(material_ids_raw)]
                except ValueError:
                    material_ids = []
        
        # Ensure colors is a list and parse if it's a JSON string
        colors = validated_data.get('colors', [])
        if isinstance(colors, str):
            try:
                colors = json.loads(colors)
            except json.JSONDecodeError:
                colors = [colors] if colors else []
        elif colors is None:
            colors = []
        validated_data['colors'] = colors
            
        # Update the product
        product = super().update(instance, validated_data)
        
        # Handle images (add new ones, don't remove existing)
        if image_uploads:
            from apps.shop.models.metadata_models import ProductImage
            for image_file in image_uploads:
                ProductImage.objects.create(product=product, image=image_file)
        
        # Handle sizes (replace existing) with proper mapping
        if size_list is not None:
            from apps.shop.models.metadata_models import ProductSize
            # IMPORTANT: Delete existing sizes first to prevent duplicates
            existing_sizes_count = product.product_sizes.count()
            product.product_sizes.all().delete()
            # print(f"DEBUG UPDATE - Deleted {existing_sizes_count} existing sizes")
            
            size_mapping = {
                # Backend enum values (exact matches)
                'XS': ProductSize.Sizes.EXTRA_SMALL,
                'SM': ProductSize.Sizes.SMALL,
                'MD': ProductSize.Sizes.MEDIUM,
                'LG': ProductSize.Sizes.LARGE,
                'XL': ProductSize.Sizes.EXTRA_LARGE,
                # Common frontend abbreviations (for compatibility)
                'EXTRA_SMALL': ProductSize.Sizes.EXTRA_SMALL,
                'S': ProductSize.Sizes.SMALL,
                'SMALL': ProductSize.Sizes.SMALL,
                'M': ProductSize.Sizes.MEDIUM,
                'MEDIUM': ProductSize.Sizes.MEDIUM,
                'L': ProductSize.Sizes.LARGE,
                'LARGE': ProductSize.Sizes.LARGE,
                'XXL': ProductSize.Sizes.EXTRA_LARGE,
                'EXTRA_LARGE': ProductSize.Sizes.EXTRA_LARGE,
            }

            print(f"DEBUG UPDATE - Creating {len(size_list)} new sizes: {size_list}")
            for size_name in size_list:
                size_key = size_name.strip().upper().replace(' ', '_')
                print(f"DEBUG UPDATE - Processing size: '{size_name}' -> '{size_key}'")
                
                # Handle special cases
                if size_key in ['ONE_SIZE', 'ONESIZE', 'ONE SIZE']:
                    ProductSize.objects.create(product=product, size=ProductSize.Sizes.MEDIUM)
                    print(f"DEBUG UPDATE - Created One Size as MEDIUM")
                elif size_key in size_mapping:
                    ProductSize.objects.create(product=product, size=size_mapping[size_key])
                    print(f"DEBUG UPDATE - Created size: {size_mapping[size_key]}")
                else:
                    # Default fallback
                    ProductSize.objects.create(product=product, size=ProductSize.Sizes.MEDIUM)
                    print(f"DEBUG UPDATE - Created fallback size: MEDIUM for '{size_name}'")
        
        # Handle categories and materials
        if category_ids is not None:
            product.categories.set(category_ids)
        if material_ids is not None:
            product.materials.set(material_ids)
            
        # print(f"DEBUG UPDATE RESULT - Product updated:")
        # print(f"  - Title: {product.title}")
        # print(f"  - Description: {product.description}")
        # print(f"  - Price: {product.price}")
        # print(f"  - Stock: {product.stock}")
        # print(f"  - Images: {product.images.count()}")
        # print(f"  - Sizes: {product.product_sizes.count()}")
        # print(f"  - Categories: {product.categories.count()}")
        # print(f"  - Materials: {product.materials.count()}")
        # print(f"  - Colors: {product.colors}")
            
        return product

class EventProductOrderSerializer(serializers.ModelSerializer):
    """
    Serializer for EventProductOrder model with comprehensive order management.
    
    Example API object:
    {
        "product": "789e0123-e89b-12d3-a456-426614174002",  // EventProduct UUID
        "cart": "345e6789-e89b-12d3-a456-426614174004",   // EventCart UUID
        "quantity": 2,
        "price_at_purchase": 25.00,
        "discount_applied": 2.50,
        "size": 1,  // ProductSize ID
        "uses_size": true,
        "status": "pending",
        "changeable": true,
        "change_requested": false,
        "change_reason": "",
        "admin_notes": "Customer requested expedited shipping"
    }
    
    Response includes additional computed fields:
    {
        "id": 1,
        "order_reference_id": "ORDCNF25ANCRD-3456789012-7890123456",
        "product_title": "Conference T-Shirt",
        "product_details": {...}, // Full EventProductSerializer data
        "cart_uuid": "345e6789-e89b-12d3-a456-426614174004",
        "cart_user_email": "user@example.com",  // cart.user.primary_email
        "size": {
            "id": 1,
            "size": "MD",
            "price_modifier": 0.0
        },
        "status_display": "Pending",
        "added": "2025-01-15T10:30:00Z",
        "time_added": "2025-01-15T10:30:00Z"
    }
    """
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_details = EventProductSerializer(source="product", read_only=True)
    cart_uuid = serializers.UUIDField(source="cart.uuid", read_only=True)
    cart_user_email = serializers.EmailField(source="cart.user.primary_email", read_only=True)
    size = ProductSizeSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    imageUrl = serializers.SerializerMethodField()
    bank_reference = serializers.SerializerMethodField()

    class Meta:
        model = EventProductOrder
        fields = [
            "id", "order_reference_id", "product", "product_title", "product_details", 
            "cart", "cart_uuid", "cart_user_email", "quantity", "added", "time_added",
            "price_at_purchase", "discount_applied", "status", "status_display", 
            "size", "uses_size", "changeable", "change_requested", "change_reason", "admin_notes", "imageUrl", "bank_reference"
        ]
        read_only_fields = ["id", "order_reference_id", "product_title", "product_details", 
                           "cart_uuid", "cart_user_email", "added", "time_added", "status_display"]
        
    def get_imageUrl(self, obj):
        # only gets the first image it sees out of multiple
        images = ProductImageSerializer(obj.product.images, many=True).data
        if images and len(images) > 0:
            return images[0].get('image_url')
        return None
    
    def get_bank_reference(self, obj):
        """
        Get the bank_reference from the associated ProductPayment for this cart.
        Since payments are linked to the cart (not individual orders), 
        we look up the payment for this product order's cart.
        """
        try:
            # Import here to avoid circular import
            from apps.shop.models.payments import ProductPayment
            
            # Get the most recent payment for this cart that has a bank_reference
            payment = ProductPayment.objects.filter(
                cart=obj.cart,
                bank_reference__isnull=False
            ).order_by('-created_at').first()
            
            if payment:
                return payment.bank_reference
            return None
        except Exception:
            return None
        
    def create(self, validated_data):
        # Set price_at_purchase from product if not provided
        if not validated_data.get('price_at_purchase') and validated_data.get('product'):
            validated_data['price_at_purchase'] = validated_data['product'].price
            
        # Set uses_size flag if size is provided
        if validated_data.get('size'):
            validated_data['uses_size'] = True
            
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle status changes
        old_status = instance.status
        new_status = validated_data.get('status')
        
        if new_status and old_status != new_status:
            # Handle specific status transitions
            if new_status == EventProductOrder.Status.PURCHASED:
                validated_data['changeable'] = False
                
        # Update uses_size flag if size is changed
        if 'size' in validated_data:
            validated_data['uses_size'] = bool(validated_data['size'])
            
        return super().update(instance, validated_data)

class EventCartSerializer(serializers.ModelSerializer):
    """
    Serializer for EventCart model with nested product order creation.
    
    Example API object:
    {
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "total": 125.50,
        "shipping_cost": 5.00,
        "approved": false,
        "submitted": false,
        "active": true,
        "notes": "Please deliver to reception",
        "shipping_address": "123 Main St, London, SW1A 1AA, UK",
        "product_orders": [
            {
                "product_id": "789e0123-e89b-12d3-a456-426614174002",
                "quantity": 2,
                "size_id": 1,
                "price_at_purchase": 25.00,
                "discount_applied": 2.50
            },
            {
                "product_id": "012e3456-e89b-12d3-a456-426614174003",
                "quantity": 1,
                "price_at_purchase": 75.00
            }
        ]
    }
    
    Response includes additional computed fields:
    {
        "uuid": "345e6789-e89b-12d3-a456-426614174004",
        "user": "USR001",
        "user_email": "user@example.com",  // user.primary_email
        "event_name": "Anchored Conference 2025",
        "order_reference_id": "ORDCNF25ANCRD-3456789012",
        "created": "2025-01-15T10:30:00Z",
        "updated": "2025-01-15T10:35:00Z",
        "orders": [...] // EventProductOrderSerializer data
    }
    """
    user = serializers.CharField(source="user.member_id", read_only=True)
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    orders = EventProductOrderSerializer(many=True, read_only=True)
    bank_reference = serializers.SerializerMethodField()
    
    # Write-only fields for creating orders
    product_orders = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of product order dicts to create with this cart"
    )
    
    def get_bank_reference(self, obj):
        # get associated payment model
        payment = obj.product_payments.first()
        if not payment:
            return None
        return payment.bank_reference
            
            

    class Meta:
        model = EventCart
        fields = [
            "uuid", "user", "user_email", "event", "event_name", "order_reference_id",
            "total", "shipping_cost", "created", "updated", "approved", "submitted", 
            "active", "cart_status", "locked_at", "lock_expires_at",  # New cart locking fields
            "notes", "shipping_address", "orders", "product_orders", "bank_reference", "created_via_admin"
        ]
        
        read_only_fields = ["uuid", "user", "user_email", "event_name", "order_reference_id", "created", "updated", 
                          "cart_status", "locked_at", "lock_expires_at"]
        
    def create(self, validated_data):
        from apps.shop.models.shop_models import EventProductOrder
        product_orders_data = validated_data.pop('product_orders', [])
        
        # Set user from request context
        if 'request' in self.context:
            validated_data['user'] = self.context['request'].user
            
        # Create the cart
        cart = super().create(validated_data)
        
        # Create associated product orders
        for order_data in product_orders_data:
            EventProductOrder.objects.create(
                cart=cart,
                product_id=order_data.get('product_id'),
                quantity=order_data.get('quantity', 1),
                size_id=order_data.get('size_id'),
                price_at_purchase=order_data.get('price_at_purchase'),
                discount_applied=order_data.get('discount_applied', 0)
            )
            
        return cart
    
    def update(self, instance, validated_data):
        from apps.shop.models.shop_models import EventProductOrder
        product_orders_data = validated_data.pop('product_orders', None)
        
        # Update the cart
        cart = super().update(instance, validated_data)
        
        # Handle product orders updates (add new orders, don't remove existing)
        if product_orders_data is not None:
            for order_data in product_orders_data:
                EventProductOrder.objects.create(
                    cart=cart,
                    product_id=order_data.get('product_id'),
                    quantity=order_data.get('quantity', 1),
                    size_id=order_data.get('size_id'),
                    price_at_purchase=order_data.get('price_at_purchase'),
                    discount_applied=order_data.get('discount_applied', 0)
                )
                
        return cart
        