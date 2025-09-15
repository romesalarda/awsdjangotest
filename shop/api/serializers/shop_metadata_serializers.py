from rest_framework import serializers
from shop.models.metadata_models import ProductCategory, ProductMaterial, ProductImage

class ProductCategorySerializer(serializers.ModelSerializer):
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
    image_url = serializers.ImageField(source="image", read_only=True)

    class Meta:
        model = ProductImage
        fields = ["uuid", "product", "product_title", "product_uuid", "image", "image_url"]