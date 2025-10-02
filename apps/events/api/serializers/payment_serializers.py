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
    """
    Serializer for EventPaymentPackage model with nested resource creation.
    
    Example API object:
    {
        "name": "Early Bird Package",
        "description": "Special discount for early registrations",
        "price": 5000,  // Price in pence (£50.00)
        "discounted_price": 4500,  // Discounted price in pence (£45.00)
        "currency": "gbp",
        "capacity": 100,
        "available_from": "2025-01-01T00:00:00Z",
        "available_until": "2025-03-01T23:59:59Z",
        "package_date_starts": "2025-01-01",
        "package_date_ends": "2025-03-01",
        "whats_included": "Access to all sessions, meals, accommodation, welcome pack",
        "main_package": true,
        "is_active": true,
        "resource_data": [
            {
                "resource_name": "Package Information PDF",
                "description": "Detailed information about what's included",
                "resource_link": "https://example.com/package-info.pdf",
                "public_resource": true
            }
        ]
    }
    """
    price_display = serializers.SerializerMethodField()
    
    # Write-only fields for nested resource creation
    resource_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of resource dicts to create and associate with this package"
    )

    class Meta:
        model = EventPaymentPackage
        fields = [
            "id", "event", "name", "description", "price", "price_display",
            "discounted_price", "currency", "capacity", "resources", "resource_data",
            "available_from", "available_until", "package_date_starts", "package_date_ends",
            "is_active", "whats_included", "main_package", "created_at", "updated_at"
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def get_price_display(self, obj):
        # Price is stored in pence, so divide by 100 for display
        return f"{obj.price / 100:.2f} {obj.currency.upper()}"
    
    def create(self, validated_data):
        from apps.events.models import EventResource
        resource_data = validated_data.pop('resource_data', [])
        
        # Create the package
        package = super().create(validated_data)
        
        # Handle resource creation
        for resource_dict in resource_data:
            resource = EventResource.objects.create(
                resource_name=resource_dict.get('resource_name', ''),
                description=resource_dict.get('description', ''),
                resource_link=resource_dict.get('resource_link', ''),
                public_resource=resource_dict.get('public_resource', False),
                added_by=self.context['request'].user if 'request' in self.context else None
            )
            package.resources.add(resource)
        
        return package
    
    def update(self, instance, validated_data):
        from apps.events.models import EventResource
        resource_data = validated_data.pop('resource_data', None)
        
        # Update the package
        package = super().update(instance, validated_data)
        
        # Handle resource updates (add new resources, don't remove existing)
        if resource_data is not None:
            for resource_dict in resource_data:
                resource = EventResource.objects.create(
                    resource_name=resource_dict.get('resource_name', ''),
                    description=resource_dict.get('description', ''),
                    resource_link=resource_dict.get('resource_link', ''),
                    public_resource=resource_dict.get('public_resource', False),
                    added_by=self.context['request'].user if 'request' in self.context else None
                )
                package.resources.add(resource)
        
        return package


class EventPaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for EventPayment model with participant relationship handling.
    
    Example API object:
    {
        "user": "123e4567-e89b-12d3-a456-426614174000",  // EventParticipant UUID
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "package": 1,  // EventPaymentPackage ID
        "method": 2,   // EventPaymentMethod ID
        "amount": 5000,  // Amount in pence (£50.00)
        "currency": "gbp",
        "status": "PENDING",
        "stripe_payment_intent": "pi_1234567890",
        "verified": false
    }
    
    Response includes additional computed fields:
    {
        "id": 1,
        "user": "123e4567-e89b-12d3-a456-426614174000",
        "participant_details": {
            "participant_id": "123e4567-e89b-12d3-a456-426614174000",
            "event_pax_id": "CNF25ANCRD-123456",
            "full_name": "John Smith",
            "email": "john@example.com",  // user.primary_email
            "participant_type": "PARTICIPANT",
            "status": "CONFIRMED",
            "registration_date": "2025-01-15T10:30:00Z"
        },
        "event_name": "Anchored Conference 2025",
        "package_name": "Early Bird Package",
        "method_display": "Bank Transfer",
        "amount_display": "50.00 GBP",
        "status_display": "Pending",
        "event_payment_tracking_number": "CNF25ANCRD-PAY-456789",
        "paid_at": null,
        "created_at": "2025-01-15T10:35:00Z"
    }
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()
    participant_details = serializers.SerializerMethodField(read_only=True)
    participant_user_email = serializers.CharField(source="user.user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    method_display = serializers.CharField(source="method.get_method_display", read_only=True)

    class Meta:
        model = EventPayment
        fields = [
            "id", "user", "participant_details", "participant_user_email", "event", "event_name", 
            "package", "package_name", "method", "method_display", "stripe_payment_intent", 
            "amount", "amount_display", "currency", "status", "status_display", 
            "event_payment_tracking_number", "paid_at", "verified", "created_at", "updated_at", "bank_reference"
        ]
        read_only_fields = ("id", "participant_details", "participant_user_email", "event_name", 
                           "package_name", "method_display", "event_payment_tracking_number", 
                           "created_at", "updated_at", "bank_reference")

    def get_amount_display(self, obj):
        return f"{obj.amount / 100:.2f} {obj.currency.upper()}"
    
    def get_participant_details(self, obj):
        """Get participant details including registration info"""
        if obj.user and obj.user.user:
            return {
                "participant_id": str(obj.user.id),
                "event_pax_id": obj.user.event_pax_id,
                "full_name": f"{obj.user.user.first_name} {obj.user.user.last_name}",
                "email": obj.user.user.primary_email,
                "participant_type": obj.user.participant_type,
                "status": obj.user.status,
                "registration_date": obj.user.registration_date,
            }
        return None
    
    def create(self, validated_data):
        # Set the event from the participant if not provided
        if not validated_data.get('event') and validated_data.get('user'):
            validated_data['event'] = validated_data['user'].event
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle status changes and paid date updates
        if 'status' in validated_data and validated_data['status'] == EventPayment.PaymentStatus.SUCCEEDED:
            if not instance.paid_at:
                instance.mark_as_paid()
        
        return super().update(instance, validated_data)
