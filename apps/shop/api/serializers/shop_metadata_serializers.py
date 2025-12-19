from rest_framework import serializers
from apps.shop.models.metadata_models import ProductCategory, ProductMaterial, ProductImage, ProductSize

class ProductCategorySerializer(serializers.ModelSerializer):
    '''
    Serializer for ProductCategory model
    '''
    product_count = serializers.IntegerField(source="eventproduct_set.count", read_only=True)

    class Meta:
        model = ProductCategory
        fields = ["id", "title", "description", "product_count"]

class ProductMaterialSerializer(serializers.ModelSerializer):

    product_count = serializers.IntegerField(source="eventproduct_set.count", read_only=True)

    class Meta:
        model = ProductMaterial
        fields = ["id", "title", "description", "product_count"]

class ProductImageSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_uuid = serializers.UUIDField(source="product.uuid", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["uuid", "product", "product_title", "product_uuid", "image", "image_url"]
    
    def get_image_url(self, obj):
        """Return absolute URL for product image"""
        if not obj.image:
            return None
        
        url = obj.image.url
        
        # If already a full URL (http/https or S3), return as-is
        if url.startswith('http://') or url.startswith('https://'):
            return url
        
        # Build absolute URL for relative paths
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        
        # Fallback: return the URL as-is
        return url
        
class ProductSizeSerializer(serializers.ModelSerializer):
    '''
    Serializer for ProductSize model with stock validation
    '''
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_uuid = serializers.UUIDField(source="product.uuid", read_only=True)
    size_display = serializers.CharField(source="get_size_display", read_only=True)
    is_available = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductSize
        fields = [
            "id", "product", "product_title", "product_uuid", 
            "size", "size_display", "quantity", "price_modifier",
            "is_available", "final_price"
        ]
        read_only_fields = ["id", "product_title", "product_uuid", "size_display", "is_available", "final_price"]
    
    def get_is_available(self, obj):
        """Check if this size variant has stock"""
        return obj.is_available()
    
    def get_final_price(self, obj):
        """Get the final price including modifier"""
        return float(obj.get_final_price())
    
    def validate_quantity(self, value):
        """Ensure quantity is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value
    
    def validate(self, attrs):
        """Additional validation for size creation/update"""
        # Check for duplicate size on creation
        if not self.instance:  # Creating new
            product = attrs.get('product')
            size = attrs.get('size')
            if product and size:
                if ProductSize.objects.filter(product=product, size=size).exists():
                    raise serializers.ValidationError({
                        "size": f"Size {size} already exists for this product."
                    })
        return attrs