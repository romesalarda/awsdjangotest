from rest_framework import serializers
from apps.shop.models.payments import ProductPaymentMethod, ProductPaymentPackage, ProductPayment
from apps.shop.models.shop_models import EventProduct, EventCart

class ProductPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPaymentMethod
        fields = "__all__"

class ProductPaymentPackageSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(many=True, queryset=EventProduct.objects.all())

    class Meta:
        model = ProductPaymentPackage
        fields = "__all__"

class ProductPaymentSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    cart_id = serializers.CharField(source="cart.uuid", read_only=True)
    method_display = serializers.CharField(source="method.get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)

    class Meta:
        model = ProductPayment
        fields = [
            "id", "user", "user_email", "cart", "cart_id", "package", "package_name",
            "method", "method_display", "stripe_payment_intent", "amount", "currency",
            "status", "status_display", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "user_email", "cart_id", "method_display", "status_display", "package_name"]