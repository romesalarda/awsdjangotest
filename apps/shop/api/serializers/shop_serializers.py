from rest_framework import serializers
from apps.shop.api.serializers.shop_metadata_serializers import (
    ProductImageSerializer, ProductCategorySerializer, ProductMaterialSerializer, ProductSizeSerializer
)
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder

class EventProductSerializer(serializers.ModelSerializer):
    '''
    Serializer for EventProduct model
    '''
    seller_email = serializers.EmailField(source="seller.email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    
    # Related model serializers
    categories = ProductCategorySerializer(many=True, read_only=True)  
    materials = ProductMaterialSerializer(many=True, read_only=True) 
    images = ProductImageSerializer(many=True, read_only=True)  # Multiple images
    product_sizes = ProductSizeSerializer(many=True, read_only=True)
    
    # Frontend compatibility fields
    imageUrl = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    inStock = serializers.BooleanField(source="in_stock", read_only=True)
    
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
        print(f"DEBUG - Getting imageUrl for {obj.title}: raw_url={url}")
        
        if url and not url.startswith('http'):
            # Make URL absolute if it's relative
            from django.conf import settings
            absolute_url = f"{settings.MEDIA_URL}{url.lstrip('/')}"
            print(f"DEBUG - Made absolute URL: {absolute_url}")
            return absolute_url
        print(f"DEBUG - Returning URL as-is: {url}")
        return url
    
    def get_sizes(self, obj):
        """Get list of available sizes"""
        return obj.available_sizes
    
    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "description", "extra_info", "event", "event_name",
            "price", "discount", "seller", "seller_email", "category", "stock", "featured", 
            "inStock", "in_stock", "imageUrl", "sizes", "colors",
            "categories", "materials", "images", "product_sizes", "maximum_order_quantity",
            "image_uploads", "size_list", "category_ids", "material_ids"
        ]
        read_only_fields = ["seller", "seller_email", "uuid", "event_name", "inStock", "in_stock", "imageUrl", "sizes"]
        
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
        
        print(f"DEBUG - Creating product with:")
        print(f"  - Images: {len(image_uploads)} files")
        print(f"  - Sizes: {size_list} (parsed from {size_list_raw})")
        print(f"  - Categories: {category_ids} (parsed from {category_ids_raw})")
        print(f"  - Materials: {material_ids} (parsed from {material_ids_raw})")
        print(f"  - Colors: {validated_data.get('colors', [])}")
        
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
            print(f"DEBUG - Processing size: '{size_name}' -> '{size_key}'")
            
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
        
        print(f"DEBUG - Product created with:")
        print(f"  - {product.images.count()} images")
        print(f"  - {product.product_sizes.count()} sizes")
        print(f"  - {product.categories.count()} categories")
        print(f"  - {product.materials.count()} materials")
        print(f"  - Colors: {product.colors}")
        print(f"  - Product sizes: {[s.size for s in product.product_sizes.all()]}")
            
        return product
    
    def update(self, instance, validated_data):
        # Extract related data
        import json
        print(f"DEBUG UPDATE - Instance: {instance.title} (ID: {instance.uuid})")
        print(f"DEBUG UPDATE - Validated data keys: {list(validated_data.keys())}")
        print(f"DEBUG UPDATE - Validated data: {validated_data}")
        
        image_uploads = validated_data.pop('image_uploads', None)
        size_list_raw = validated_data.pop('size_list', None)
        category_ids_raw = validated_data.pop('category_ids', None)
        material_ids_raw = validated_data.pop('material_ids', None)
        
        print(f"DEBUG UPDATE - Extracted data: images={len(image_uploads) if image_uploads else 0}, sizes={size_list_raw}, categories={category_ids_raw}, materials={material_ids_raw}")
        
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
            print(f"DEBUG UPDATE - Deleted {existing_sizes_count} existing sizes")
            
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
            
        print(f"DEBUG UPDATE RESULT - Product updated:")
        print(f"  - Title: {product.title}")
        print(f"  - Description: {product.description}")
        print(f"  - Price: {product.price}")
        print(f"  - Stock: {product.stock}")
        print(f"  - Images: {product.images.count()}")
        print(f"  - Sizes: {product.product_sizes.count()}")
        print(f"  - Categories: {product.categories.count()}")
        print(f"  - Materials: {product.materials.count()}")
        print(f"  - Colors: {product.colors}")
            
        return product

class EventProductOrderSerializer(serializers.ModelSerializer):
    '''
    Serializer for EventProductOrder model
    '''
    product_title = serializers.CharField(source="product.title", read_only=True)
    cart_uuid = serializers.UUIDField(source="cart.uuid", read_only=True)
    cart_user_email = serializers.EmailField(source="cart.user.email", read_only=True)
    size = ProductSizeSerializer(read_only=True)

    class Meta:
        model = EventProductOrder
        fields = [
            "id", "product", "product_title", "cart", "cart_uuid", "cart_user_email",
            "quantity", "added", "price_at_purchase", "discount_applied", "status", "size", "time_added"
        ]

class EventCartSerializer(serializers.ModelSerializer):
    '''
    Serializer for EventCart model
    '''
    user = serializers.CharField(source="user.member_id", read_only=True)
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    orders = EventProductOrderSerializer(many=True, read_only=True)

    class Meta:
        model = EventCart
        fields = [
            "uuid", "user", "user_email", "event", "event_name", "total", "shipping_cost",
            "created", "updated", "orders"
        ]
        
        read_only_fields = ["total", "created", "updated"]
        