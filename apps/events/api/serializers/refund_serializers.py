"""
Serializers for participant refund management.
Handles refund tracking, processing, and financial reconciliation.
"""
from rest_framework import serializers
from apps.events.models import ParticipantRefund, EventParticipant, Event
from apps.users.api.serializers import CommunityUserSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class RefundParticipantSerializer(serializers.ModelSerializer):
    """Simplified participant info for refund display"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = EventParticipant
        fields = [
            'event_pax_id',
            'full_name',
            'status'
        ]
    
    def get_full_name(self, obj):
        return obj.user.get_full_name() if obj.user else "Unknown"


class RefundEventSerializer(serializers.ModelSerializer):
    """Simplified event info for refund display"""
    
    class Meta:
        model = Event
        fields = [
            'id',
            'name',
            'event_code',
            'start_date',
            'end_date'
        ]


class ParticipantRefundListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for refund list views.
    Optimized for performance with minimal nested data.
    """
    participant_name = serializers.SerializerMethodField()
    participant_email = serializers.CharField(source='participant.user.primary_email', read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_code = serializers.CharField(source='event.event_code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_pending = serializers.SerializerMethodField()
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'id',
            'refund_reference',
            'participant_name',
            'participant_email',
            'event_name',
            'event_code',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'removal_reason',
            'currency',
            'status',
            'status_display',
            'organizer_contact_email',
            'created_at',
            'processed_at',
            'days_pending'
        ]
    
    def get_participant_name(self, obj):
        return obj.participant.user.get_full_name() if obj.participant and obj.participant.user else "Unknown"
    
    def get_days_pending(self, obj):
        """Calculate days since refund was created"""
        if obj.status == ParticipantRefund.RefundStatus.PROCESSED:
            return 0
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        return delta.days


class ParticipantRefundDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for detailed refund views.
    Includes full participant, event, and processing information.
    """
    participant = RefundParticipantSerializer(read_only=True)
    event = RefundEventSerializer(read_only=True)
    removed_by_name = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'id',
            'refund_reference',
            'participant',
            'event',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'currency',
            'status',
            'status_display',
            'removal_reason',
            'removed_by',
            'removed_by_name',
            'processed_by',
            'processed_by_name',
            'processing_notes',
            'participant_email',
            'organizer_contact_email',
            'original_payment_method',
            'refund_method',
            'created_at',
            'updated_at',
            'processed_at'
        ]
        read_only_fields = [
            'refund_reference',
            'removed_by',
            'created_at',
            'updated_at'
        ]
    
    def get_removed_by_name(self, obj):
        return obj.removed_by.get_full_name() if obj.removed_by else "System"
    
    def get_processed_by_name(self, obj):
        return obj.processed_by.get_full_name() if obj.processed_by else None


class ProcessRefundSerializer(serializers.Serializer):
    """
    Serializer for processing refund completion.
    Validates refund processing data and updates status.
    """
    processing_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional notes about the refund processing"
    )
    refund_method = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Method used to process the refund (e.g., 'Bank Transfer', 'PayPal')"
    )
    
    def validate(self, data):
        """Ensure refund can be processed"""
        refund = self.context.get('refund')
        
        if not refund:
            raise serializers.ValidationError("Refund instance required in context")
        
        if refund.status == ParticipantRefund.RefundStatus.PROCESSED:
            raise serializers.ValidationError("This refund has already been processed")
        
        if refund.status == ParticipantRefund.RefundStatus.CANCELLED:
            raise serializers.ValidationError("Cannot process a cancelled refund")
        
        return data
    
    def save(self):
        """Process the refund"""
        from django.utils import timezone
        
        refund = self.context['refund']
        user = self.context['request'].user
        
        refund.status = ParticipantRefund.RefundStatus.PROCESSED
        refund.processed_by = user
        refund.processed_at = timezone.now()
        
        if self.validated_data.get('processing_notes'):
            refund.processing_notes = self.validated_data['processing_notes']
        
        if self.validated_data.get('refund_method'):
            refund.refund_method = self.validated_data['refund_method']
        
        refund.save()
        
        return refund


class CreateRefundSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new refund records.
    Typically used internally when participants are cancelled.
    """
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'participant',
            'event',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'removal_reason',
            'removed_by',
            'participant_email',
            'organizer_contact_email',
            'original_payment_method'
        ]
    
    def validate(self, data):
        """Validate refund data"""
        # Ensure total matches individual amounts
        total = data.get('event_payment_amount', 0) + data.get('product_payment_amount', 0)
        if data.get('total_refund_amount') and data['total_refund_amount'] != total:
            data['total_refund_amount'] = total
        
        # Ensure participant belongs to event
        if data['participant'].event != data['event']:
            raise serializers.ValidationError("Participant does not belong to this event")
        
        return data
