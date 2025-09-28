from rest_framework import serializers
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder
from apps.shop.models.metadata_models import ProductSize


class EventProductDisplaySerializer(serializers.ModelSerializer):
    """
    Simplified serializer for EventProduct - optimized for display purposes.
    Removes verbose product details and focuses on essential display information.
    """
    event_name = serializers.CharField(source="event.name", read_only=True)
    seller_email = serializers.EmailField(source="seller.primary_email", read_only=True)
    imageUrl = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    inStock = serializers.BooleanField(source="in_stock", read_only=True)

    def get_imageUrl(self, obj):
        """Get the primary image URL"""
        url = obj.primary_image_url
        if url and not url.startswith('http'):
            from django.conf import settings
            return f"{settings.MEDIA_URL}{url.lstrip('/')}"
        return url

    def get_sizes(self, obj):
        """Get list of available sizes"""
        return obj.available_sizes

    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "description", "event", "event_name", 
            "price", "discount", "seller", "seller_email", "category", 
            "stock", "featured", "inStock", "imageUrl", "sizes", 
            "colors", "maximum_order_quantity"
        ]


class ProductSizeDisplaySerializer(serializers.ModelSerializer):
    """
    Simplified serializer for ProductSize - display purposes only.
    """
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_uuid = serializers.UUIDField(source="product.uuid", read_only=True)

    class Meta:
        model = ProductSize
        fields = [
            "id", "product", "product_title", "product_uuid", 
            "size", "price_modifier"
        ]


class EventProductOrderDisplaySerializer(serializers.ModelSerializer):
    """
    Simplified serializer for EventProductOrder - optimized for display purposes.
    Removes verbose product_details and focuses on essential order information.
    """
    product_title = serializers.CharField(source="product.title", read_only=True)
    cart_uuid = serializers.UUIDField(source="cart.uuid", read_only=True)
    cart_user_email = serializers.EmailField(source="cart.user.primary_email", read_only=True)
    size = ProductSizeDisplaySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = EventProductOrder
        fields = [
            "id", "order_reference_id", "product", "product_title",
            "cart", "cart_uuid", "cart_user_email", "quantity", 
            "added", "time_added", "price_at_purchase", "discount_applied", 
            "status", "status_display", "size", "uses_size", 
            "changeable", "change_requested", "change_reason", "admin_notes"
        ]


class EventCartDisplaySerializer(serializers.ModelSerializer):
    """
    Simplified serializer for EventCart - optimized for display purposes.
    Uses simplified order serializer to reduce payload size and complexity.
    """
    user = serializers.CharField(source="user.member_id", read_only=True)
    user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    orders = EventProductOrderDisplaySerializer(many=True, read_only=True)

    class Meta:
        model = EventCart
        fields = [
            "uuid", "user", "user_email", "event", "event_name", 
            "order_reference_id", "total", "shipping_cost", 
            "created", "updated", "approved", "submitted", 
            "active", "notes", "shipping_address", "orders"
        ]


class EventProductOrderMinimalSerializer(serializers.ModelSerializer):
    """
    Ultra-minimal serializer for EventProductOrder - for embedded use in carts.
    Contains only the most essential information without nested product details.
    """
    product_title = serializers.CharField(source="product.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    size_name = serializers.CharField(source="size.size", read_only=True)
    price_modifier = serializers.DecimalField(source="size.price_modifier", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = EventProductOrder
        fields = [
            "id", "order_reference_id", "product", "product_title",
            "quantity", "price_at_purchase", "discount_applied", 
            "status", "status_display", "size_name", "price_modifier",
            "uses_size", "changeable"
        ]


class EventCartMinimalSerializer(serializers.ModelSerializer):
    """
    Ultra-minimal serializer for EventCart - for list views and quick previews.
    Uses minimal order serializer to keep payload extremely light.
    """
    # user = serializers.CharField(source="user.member_id", read_only=True)
    # user_email = serializers.EmailField(source="user.primary_email", read_only=True)
    # event_name = serializers.CharField(source="event.name", read_only=True)
    orders = EventProductOrderMinimalSerializer(many=True, read_only=True)
    order_count = serializers.SerializerMethodField()

    def get_order_count(self, obj):
        """Get total number of orders in cart"""
        return obj.orders.count()

    class Meta:
        model = EventCart
        fields = [
            "uuid",
            "order_reference_id", "total", "shipping_cost", 
            "created", "approved", "submitted", "active", 
            "orders", "order_count"
        ]


class EventProductLightSerializer(serializers.ModelSerializer):
    """
    Light serializer for EventProduct - for reference in orders without full details.
    """
    event_name = serializers.CharField(source="event.name", read_only=True)
    imageUrl = serializers.SerializerMethodField()
    inStock = serializers.BooleanField(source="in_stock", read_only=True)

    def get_imageUrl(self, obj):
        """Get the primary image URL"""
        url = obj.primary_image_url
        if url and not url.startswith('http'):
            from django.conf import settings
            return f"{settings.MEDIA_URL}{url.lstrip('/')}"
        return url

    class Meta:
        model = EventProduct
        fields = [
            "uuid", "title", "event", "event_name", "price", 
            "category", "inStock", "imageUrl"
        ]