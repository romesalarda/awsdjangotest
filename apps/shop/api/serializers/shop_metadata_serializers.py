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
    Serializer for ProductSize model
    '''
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_uuid = serializers.UUIDField(source="product.uuid", read_only=True)

    class Meta:
        model = ProductSize
        fields = ["id", "product", "product_title", "product_uuid", "size", "price_modifier"]