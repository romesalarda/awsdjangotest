from rest_framework import serializers
from apps.events.models import EventPaymentMethod, EventPaymentPackage, EventPayment, DonationPayment


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
        "price": 50.00,  // Price in pounds (£50.00)
        "discounted_price": 45.00,  // User-specific discounted price (£45.00)
        "currency": "gbp",
        "capacity": 100,
        "available_from": "2025-01-01T00:00:00Z",
        "available_until": "2025-03-01T23:59:59Z",
        "package_date_starts": "2025-01-01",
        "package_date_ends": "2025-03-01",
        "whats_included": "Access to all sessions, meals, accommodation, welcome pack",
        "main_package": true,
        "is_active": true,
        "user_discount_info": {  // Added for authenticated users with discounts
            "original_price": 50.00,
            "discounted_price": 45.00,
            "discount_amount": 5.00,
            "discount_type": "PERCENTAGE",
            "discount_value": 10.00,
            "discount_source": "role",
            "service_team_role": "Volunteer"
        },
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
    user_discount_info = serializers.SerializerMethodField(read_only=True)
    
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
            "is_active", "whats_included", "main_package", "created_at", "updated_at",
            "user_discount_info"
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def get_price_display(self, obj):
        # Price is stored in pounds (DecimalField)
        return f"{obj.price:.2f} {obj.currency.upper()}"
    
    def get_user_discount_info(self, obj):
        """
        Get user-specific discount information for this package.
        Returns discount details based on service team membership and role.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            # For unauthenticated users, check package-level discount only
            if obj.discounted_price and obj.discounted_price > 0 and obj.discounted_price < obj.price:
                from decimal import Decimal
                original = Decimal(str(obj.price))
                discounted = Decimal(str(obj.discounted_price))
                return {
                    'original_price': float(original),
                    'discounted_price': float(discounted),
                    'discount_amount': float(original - discounted),
                    'discount_type': None,
                    'discount_value': None,
                    'discount_source': 'package',
                    'service_team_role': None,
                }
            return None
        
        # Get user-specific pricing with discount priority
        discount_info = obj.get_user_discounted_price(request.user)
        
        # Only return if there's an actual discount
        if discount_info['discount_amount'] > 0:
            return {
                'original_price': float(discount_info['original_price']),
                'discounted_price': float(discount_info['discounted_price']),
                'discount_amount': float(discount_info['discount_amount']),
                'discount_type': discount_info['discount_type'],
                'discount_value': float(discount_info['discount_value']) if discount_info['discount_value'] else None,
                'discount_source': discount_info['discount_source'],
                'service_team_role': discount_info['service_team_role'],
            }
        
        return None
    
    def to_representation(self, instance):
        """
        Override discounted_price field to show user-specific pricing.
        For authenticated service team members, show their calculated discounted price.
        """
        data = super().to_representation(instance)
        
        user_discount = data.get('user_discount_info')
        if user_discount:
            # Override discounted_price with user-specific value
            data['discounted_price'] = user_discount['discounted_price']
        
        return data
    
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
        "amount": 50.00,  // Amount in pounds (£50.00)
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
        return f"{obj.amount:.2f} {obj.currency.upper()}"
    
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


class EventPaymentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing event payments in participant management views.
    Optimized for minimal data transfer with essential payment and participant info.
    """
    participant_id = serializers.CharField(source="user.id", read_only=True)
    participant_name = serializers.SerializerMethodField()
    participant_email = serializers.CharField(source="user.user.primary_email", read_only=True)
    participant_event_pax_id = serializers.CharField(source="user.event_pax_id", read_only=True)
    participant_area = serializers.SerializerMethodField()
    participant_chapter = serializers.SerializerMethodField()
    
    payment_method = serializers.CharField(source="method.get_method_display", read_only=True)
    payment_method_type = serializers.CharField(source="method.method", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    package_price = serializers.DecimalField(source="package.price", max_digits=10, decimal_places=2, read_only=True)
    
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()
    
    class Meta:
        model = EventPayment
        fields = [
            "id", "participant_id", "participant_name", "participant_email", 
            "participant_event_pax_id", "participant_area", "participant_chapter",
            "event_payment_tracking_number", "bank_reference",
            "payment_method", "payment_method_type", "package_name", "package_price",
            "amount", "amount_display", "currency", 
            "status", "status_display", "verified",
            "paid_at", "created_at"
        ]
    
    def get_participant_name(self, obj):
        if obj.user and obj.user.user:
            return f"{obj.user.user.first_name} {obj.user.user.last_name}"
        return "Unknown"
    
    def get_participant_area(self, obj):
        if obj.user and obj.user.user and hasattr(obj.user.user, 'area_from') and obj.user.user.area_from:
            return obj.user.user.area_from.area_name
        return None
    
    def get_participant_chapter(self, obj):
        if obj.user and obj.user.user and hasattr(obj.user.user, 'area_from') and obj.user.user.area_from:
            area = obj.user.user.area_from
            if hasattr(area, 'unit') and area.unit and hasattr(area.unit, 'chapter') and area.unit.chapter:
                return area.unit.chapter.chapter_name
        return None
    
    def get_amount_display(self, obj):
        return f"£{obj.amount:.2f}"


class DonationPaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for DonationPayment model with participant and event relationship handling.
    
    Handles donation payments made by participants for specific events, including:
    - Tracking donation amounts and payment methods
    - Linking donations to events and participants
    - Supporting Stripe payment integration
    - Maintaining payment status and verification
    
    Example API object:
    {
        "user": "123e4567-e89b-12d3-a456-426614174000",  // EventParticipant UUID
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "method": 2,   // EventPaymentMethod ID
        "amount": 25.00,  // Donation amount in pounds (£25.00)
        "currency": "gbp",
        "status": "PENDING",
        "stripe_payment_intent": "pi_1234567890",
        "event_payment_tracking_number": "DON-2025-001234",
        "bank_reference": "SMITH-DONATION-001",
        "verified": false,
        "pay_to_event": true
    }
    
    Response includes additional computed fields:
    {
        "id": "789e0123-e89b-12d3-a456-426614174002",
        "user": "123e4567-e89b-12d3-a456-426614174000",
        "participant_details": {
            "participant_id": "123e4567-e89b-12d3-a456-426614174000",
            "event_pax_id": "CNF25ANCRD-123456",
            "full_name": "John Smith",
            "email": "john@example.com",
            "participant_type": "PARTICIPANT",
            "status": "CONFIRMED"
        },
        "event": "456e7890-e89b-12d3-a456-426614174001",
        "event_name": "Anchored Conference 2025",
        "method": 2,
        "method_display": "Bank Transfer",
        "stripe_payment_intent": "pi_1234567890",
        "amount": "25.00",
        "amount_display": "£25.00 GBP",
        "currency": "gbp",
        "status": "PENDING",
        "status_display": "Pending",
        "event_payment_tracking_number": "DON-2025-001234",
        "bank_reference": "SMITH-DONATION-001",
        "verified": false,
        "pay_to_event": true,
        "created_at": "2025-01-15T10:35:00Z",
        "paid_at": null,
        "updated_at": "2025-01-15T10:35:00Z"
    }
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()
    participant_details = serializers.SerializerMethodField(read_only=True)
    # participant_user_email = serializers.CharField(source="user.user.primary_email", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    method_display = serializers.CharField(source="method.get_method_display", read_only=True)

    class Meta:
        model = DonationPayment
        fields = [
            "id", "user", "participant_details", 
            "event", "event_name", "method", "method_display", 
            "amount", "amount_display", "currency", 
            "status", "status_display", "event_payment_tracking_number", 
            "bank_reference", "verified", "pay_to_event", 
            "paid_at", "created_at", "updated_at"
        ]
        read_only_fields = (
            "id", "participant_details", 
            "event_name", "method_display", "created_at", "updated_at"
        )

    def get_amount_display(self, obj):
        """Format amount with currency symbol"""
        return f"£{obj.amount:.2f} {obj.currency.upper()}"
    
    def get_participant_details(self, obj):
        """
        Get participant details including registration info.
        Returns comprehensive participant information for donation tracking.
        """
        if obj.user and obj.user.user:
            user = obj.user.user
            details = {
                "participant_id": str(obj.user.id),
                "event_pax_id": obj.user.event_pax_id,
                "full_name": f"{user.first_name} {user.last_name}",
                "email": user.primary_email,
                "phone": user.contact_number if hasattr(user, 'contact_number') else None,
                "participant_type": obj.user.participant_type,
                "status": obj.user.status,
                "area": None,
                "chapter": None,
            }
            
            # Add area and chapter information
            if hasattr(user, 'area_from') and user.area_from:
                details["area"] = user.area_from.area_name
                if hasattr(user.area_from, 'unit') and user.area_from.unit:
                    if hasattr(user.area_from.unit, 'chapter') and user.area_from.unit.chapter:
                        details["chapter"] = user.area_from.unit.chapter.chapter_name
            
            return details
        return None
    
    def validate(self, attrs):
        """
        Validate donation payment data.
        Ensures event and participant are properly linked.
        """
        # Validate that user (participant) belongs to the event
        user = attrs.get('user')
        event = attrs.get('event')
        
        if user and event and user.event != event:
            raise serializers.ValidationError({
                "user": "Participant must be registered for the specified event."
            })
        
        # Validate amount is positive
        amount = attrs.get('amount')
        if amount and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Donation amount must be greater than zero."
            })
        
        return attrs
    
    def create(self, validated_data):
        """
        Create a new donation payment.
        Automatically sets the event from the participant if not provided.
        """
        # Set the event from the participant if not provided
        if not validated_data.get('event') and validated_data.get('user'):
            validated_data['event'] = validated_data['user'].event
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """
        Update donation payment.
        Handles status changes and payment confirmation.
        """
        # Handle status changes and paid date updates
        if 'status' in validated_data:
            new_status = validated_data['status']
            if new_status == DonationPayment.PaymentStatus.SUCCEEDED and not instance.paid_at:
                from django.utils import timezone
                instance.paid_at = timezone.now()
        
        return super().update(instance, validated_data)


class DonationPaymentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing donation payments.
    Optimized for minimal data transfer with essential donation and participant info.
    
    Used in list views and dashboards where full donation details aren't needed.
    """
    participant_id = serializers.CharField(source="user.id", read_only=True)
    participant_name = serializers.SerializerMethodField()
    participant_email = serializers.CharField(source="user.user.primary_email", read_only=True)
    participant_event_pax_id = serializers.CharField(source="user.event_pax_id", read_only=True)
    participant_area = serializers.SerializerMethodField()
    participant_chapter = serializers.SerializerMethodField()
    
    event_name = serializers.CharField(source="event.name", read_only=True)
    payment_method = serializers.CharField(source="method.get_method_display", read_only=True)
    payment_method_type = serializers.CharField(source="method.method", read_only=True)
    
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    amount_display = serializers.SerializerMethodField()
    
    class Meta:
        model = DonationPayment
        fields = [
            "id", "participant_id", "participant_name", "participant_email", 
            "participant_event_pax_id", "participant_area", "participant_chapter",
            "event_name", "event_payment_tracking_number", "bank_reference",
            "payment_method", "payment_method_type",
            "amount", "amount_display", "currency", 
            "status", "status_display", "verified", "pay_to_event",
            "paid_at", "created_at"
        ]
    
    def get_participant_name(self, obj):
        """Get formatted participant name or fallback"""
        if obj.user and obj.user.user:
            return f"{obj.user.user.first_name} {obj.user.user.last_name}"
        return "Unknown"
    
    def get_participant_area(self, obj):
        """Get participant's area name"""
        if obj.user and obj.user.user and hasattr(obj.user.user, 'area_from') and obj.user.user.area_from:
            return obj.user.user.area_from.area_name
        return None
    
    def get_participant_chapter(self, obj):
        """Get participant's chapter name"""
        if obj.user and obj.user.user and hasattr(obj.user.user, 'area_from') and obj.user.user.area_from:
            area = obj.user.user.area_from
            if hasattr(area, 'unit') and area.unit and hasattr(area.unit, 'chapter') and area.unit.chapter:
                return area.unit.chapter.chapter_name
        return None
    
    def get_amount_display(self, obj):
        """Format amount with currency symbol"""
        return f"£{obj.amount:.2f}"
