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
    categories = ProductCategorySerializer(many=True, read_only=True)  
    materials = ProductMaterialSerializer(many=True, read_only=True) 

    images = ProductImageSerializer(many=True, read_only=True)  # uses related_name="images"
    sizes = ProductSizeSerializer(many=True, read_only=True, source="product_sizes")  # TODO: just turn this into a list of available sizes
    
    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "description", "extra_info", "event", "event_name",
            "price", "discount", "seller", "seller_email", "categories", "materials", "images", "sizes"
        ]

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
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    # products = EventProductSerializer(many=True, read_only=True)
    orders = EventProductOrderSerializer(many=True, read_only=True)

    class Meta:
        model = EventCart
        fields = [
            "uuid", "user", "user_email", "event", "event_name", "total", "shipping_cost",
            "created", "updated", "orders"
        ]
        
        read_only_fields = ["total", "created", "updated"]
        