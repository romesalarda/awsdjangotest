from rest_framework import serializers
from apps.shop.api.serializers.shop_metadata_serializers import ProductImageSerializer, ProductCategorySerializer, ProductMaterialSerializer
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder

class EventProductSerializer(serializers.ModelSerializer):
    '''
    Serializer for EventProduct model
    '''
    seller_email = serializers.EmailField(source="seller.email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    categories = ProductCategorySerializer(many=True, read_only=True)  
    materials = ProductMaterialSerializer(many=True, read_only=True) 

    images = ProductImageSerializer(many=True, read_only=True)  # uses related_name="images"

    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "description", "extra_info", "event", "event_name",
            "size", "price", "discount", "seller", "seller_email", "categories", "materials", "images"
        ]

class EventCartSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    products = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    orders = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = EventCart
        fields = [
            "uuid", "user", "user_email", "event", "event_name", "total", "shipping_cost",
            "approved", "submitted", "active", "products", "orders", "notes", "shipping_address",
            "created", "updated"
        ]

class EventProductOrderSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    cart_uuid = serializers.UUIDField(source="cart.uuid", read_only=True)
    cart_user_email = serializers.EmailField(source="cart.user.email", read_only=True)

    class Meta:
        model = EventProductOrder
        fields = [
            "id", "product", "product_title", "cart", "cart_uuid", "cart_user_email",
            "quantity", "added", "price_at_purchase", "discount_applied", "status"
        ]