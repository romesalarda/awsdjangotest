from rest_framework import serializers
from apps.events.models import EventPaymentMethod, EventPaymentPackage, EventPayment


class EventPaymentMethodSerializer(serializers.ModelSerializer):
    '''
    Serializer for the EventPaymentMethod model. Describes what payment methods are available for an event.
    '''
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = EventPaymentMethod
        fields = [
            "id", "event", "method", "method_display",
            "account_name", "account_number", "sort_code",
            "reference_example", "reference_instruction", "important_information",
            "fee_add_on", "percentage_fee_add_on", "currency",
            "instructions", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at")


class EventPaymentPackageSerializer(serializers.ModelSerializer):
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = EventPaymentPackage
        fields = [
            "id", "event", "name", "description", "price", "price_display",
            "currency", "capacity", "resources",
            "available_from", "available_until",
            "is_active", "created_at", "updated_at", "whats_included"
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def get_price_display(self, obj):
        return f"{obj.price :.2f} {obj.currency.upper()}"


class EventPaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = EventPayment
        fields = [
            "id", "user", "event", "package", "method",
            "stripe_payment_intent", "amount", "amount_display", "currency",
            "status", "status_display", "created_at", "updated_at"
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def get_amount_display(self, obj):
        return f"{obj.amount / 100:.2f} {obj.currency.upper()}"
