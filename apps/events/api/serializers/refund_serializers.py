"""
Serializers for participant refund management.
Handles refund tracking, processing, and financial reconciliation.
Supports both automatic (Stripe) and manual (bank transfer) refunds.
"""
from rest_framework import serializers
from apps.events.models import ParticipantRefund, EventParticipant, Event, EventPayment, EventServiceTeamMember, EventRole
from apps.shop.models import ProductPayment
from apps.users.api.serializers import CommunityUserSerializer
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

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
    participant_email = serializers.CharField(read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_code = serializers.CharField(source='event.event_code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    refund_reason_display = serializers.CharField(source='get_refund_reason_display', read_only=True)
    days_pending = serializers.SerializerMethodField()
    can_process = serializers.SerializerMethodField()
    initiated_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'id',
            'refund_reference',
            'participant',
            'participant_name',
            'participant_email',
            'event',
            'event_name',
            'event_code',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'removal_reason_details',
            'currency',
            'status',
            'status_display',
            'refund_reason',
            'refund_reason_display',
            'is_automatic_refund',
            'refund_contact_email',
            'initiated_by_name',
            'created_at',
            'processed_at',
            'days_pending',
            'can_process',
            'participant_notified',
            'secretariat_notified'
        ]
    
    def get_participant_name(self, obj):
        return obj.participant_name or (
            obj.participant.user.get_full_name() if obj.participant and obj.participant.user else "Unknown"
        )
    
    def get_days_pending(self, obj):
        """Calculate days since refund was created"""
        if obj.status == ParticipantRefund.RefundStatus.PROCESSED:
            return 0
        delta = timezone.now() - obj.created_at
        return delta.days
    
    def get_can_process(self, obj):
        can_process, message = obj.can_process_refund()
        return {
            'allowed': can_process,
            'message': message
        }
    
    def get_initiated_by_name(self, obj):
        if not obj.removed_by:
            return "System"
        return obj.removed_by.get_full_name() if hasattr(obj.removed_by, 'get_full_name') else obj.removed_by.email


class ParticipantRefundDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for detailed refund views.
    Includes full participant, event, payment, and processing information.
    """
    participant = RefundParticipantSerializer(read_only=True)
    event = RefundEventSerializer(read_only=True)
    removed_by_name = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    refund_reason_display = serializers.CharField(source='get_refund_reason_display', read_only=True)
    can_process = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'id',
            'refund_reference',
            'participant',
            'event',
            'event_payment',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'currency',
            'status',
            'status_display',
            'refund_reason',
            'refund_reason_display',
            'removal_reason_details',
            'removed_by',
            'removed_by_name',
            'processed_by',
            'processed_by_name',
            'processing_notes',
            'participant_email',
            'participant_name',
            'refund_contact_email',
            'original_payment_method',
            'is_automatic_refund',
            'refund_method',
            'stripe_refund_id',
            'stripe_failure_reason',
            'bank_account_name',
            'bank_account_number',
            'bank_sort_code',
            'participant_notified',
            'secretariat_notified',
            'created_at',
            'updated_at',
            'processed_at',
            'can_process',
            'payment_details',
            'timeline'
        ]
        read_only_fields = [
            'refund_reference',
            'removed_by',
            'created_at',
            'updated_at'
        ]
    
    def get_removed_by_name(self, obj):
        if not obj.removed_by:
            return "System"
        return obj.removed_by.get_full_name() if hasattr(obj.removed_by, 'get_full_name') else obj.removed_by.email
    
    def get_processed_by_name(self, obj):
        if not obj.processed_by:
            return None
        return obj.processed_by.get_full_name() if hasattr(obj.processed_by, 'get_full_name') else obj.processed_by.email
    
    def get_can_process(self, obj):
        can_process, message = obj.can_process_refund()
        return {
            'allowed': can_process,
            'message': message
        }
    
    def get_payment_details(self, obj):
        """Get detailed information about original payments"""
        details = {
            'event_payment': None,
            'product_payments': []
        }
        
        if obj.event_payment:
            details['event_payment'] = {
                'id': obj.event_payment.id,
                'tracking_number': obj.event_payment.event_payment_tracking_number,
                'amount': float(obj.event_payment.amount),
                'payment_method': obj.event_payment.method.get_method_display() if obj.event_payment.method else None,
                'stripe_payment_intent': obj.event_payment.stripe_payment_intent,
                'paid_at': obj.event_payment.paid_at,
                'status': obj.event_payment.get_status_display()
            }
        
        if obj.product_payments.exists():
            details['product_payments'] = [
                {
                    'id': pp.id,
                    'reference': pp.payment_reference_id,
                    'amount': float(pp.amount),
                    'payment_method': pp.method.get_method_display() if pp.method else None,
                    'stripe_payment_intent': pp.stripe_payment_intent
                }
                for pp in obj.product_payments.all()
            ]
        
        return details
    
    def get_timeline(self, obj):
        """Generate timeline of refund events"""
        timeline = [
            {
                'event': 'Refund Created',
                'timestamp': obj.created_at,
                'by': self.get_removed_by_name(obj),
                'status': 'PENDING',
                'notes': obj.removal_reason_details[:100] if obj.removal_reason_details else None
            }
        ]
        
        if obj.status == ParticipantRefund.RefundStatus.IN_PROGRESS:
            timeline.append({
                'event': 'Refund In Progress',
                'timestamp': obj.updated_at,
                'status': 'IN_PROGRESS'
            })
        
        if obj.processed_at:
            timeline.append({
                'event': 'Refund Processed',
                'timestamp': obj.processed_at,
                'by': self.get_processed_by_name(obj),
                'status': 'PROCESSED',
                'notes': obj.processing_notes[:100] if obj.processing_notes else None
            })
        
        if obj.status == ParticipantRefund.RefundStatus.FAILED:
            timeline.append({
                'event': 'Refund Failed',
                'timestamp': obj.updated_at,
                'status': 'FAILED',
                'notes': obj.stripe_failure_reason
            })
        
        return timeline


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
    bank_account_name = serializers.CharField(required=False, allow_blank=True)
    bank_account_number = serializers.CharField(required=False, allow_blank=True)
    bank_sort_code = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Ensure refund can be processed"""
        refund = self.context.get('refund')
        
        if not refund:
            raise serializers.ValidationError("Refund instance required in context")
        
        can_process, message = refund.can_process_refund()
        if not can_process:
            raise serializers.ValidationError(message)
        
        if refund.status == ParticipantRefund.RefundStatus.PROCESSED:
            raise serializers.ValidationError("This refund has already been processed")
        
        if refund.status == ParticipantRefund.RefundStatus.CANCELLED:
            raise serializers.ValidationError("Cannot process a cancelled refund")
        
        # If manual refund, require bank details or processing notes
        if not refund.is_automatic_refund:
            if not data.get('processing_notes') and not data.get('bank_account_number'):
                raise serializers.ValidationError(
                    "Manual refunds require either processing notes or bank transfer details"
                )
        
        return data
    
    def save(self):
        """Process the refund"""
        refund = self.context['refund']
        user = self.context['request'].user
        
        refund.status = ParticipantRefund.RefundStatus.PROCESSED
        refund.processed_by = user
        refund.processed_at = timezone.now()
        
        if self.validated_data.get('processing_notes'):
            refund.processing_notes = self.validated_data['processing_notes']
        
        if self.validated_data.get('refund_method'):
            refund.refund_method = self.validated_data['refund_method']
        
        if self.validated_data.get('bank_account_name'):
            refund.bank_account_name = self.validated_data['bank_account_name']
        if self.validated_data.get('bank_account_number'):
            refund.bank_account_number = self.validated_data['bank_account_number']
        if self.validated_data.get('bank_sort_code'):
            refund.bank_sort_code = self.validated_data['bank_sort_code']
        
        refund.save()
        
        return refund


class CreateRefundSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new refund records.
    Typically used internally when participants are cancelled.
    Automatically determines contact emails and refund processing type.
    """
    
    class Meta:
        model = ParticipantRefund
        fields = [
            'participant',
            'event',
            'event_payment',
            'event_payment_amount',
            'product_payment_amount',
            'total_refund_amount',
            'refund_reason',
            'removal_reason_details',
            'removed_by',
            'participant_email',
            'participant_name',
            'refund_contact_email',
            'original_payment_method',
            'is_automatic_refund',
            'bank_account_name',
            'bank_account_number',
            'bank_sort_code'
        ]
        read_only_fields = ['removed_by']
    
    def validate(self, data):
        """Validate refund data"""
        participant = data.get('participant')
        event = data.get('event')
        event_payment = data.get('event_payment')
        event_payment_amount = data.get('event_payment_amount', Decimal('0.00'))
        product_payment_amount = data.get('product_payment_amount', Decimal('0.00'))
        
        # Ensure participant belongs to event
        if participant.event.id != event.id:
            raise serializers.ValidationError({
                'participant': "Participant does not belong to this event"
            })
        
        # Check refund deadline
        refund_deadline = event.refund_deadline or event.payment_deadline
        if refund_deadline and timezone.now() > refund_deadline:
            raise serializers.ValidationError({
                'event': f'Refund deadline has passed ({refund_deadline.strftime("%Y-%m-%d")})'
            })
        
        # Check if event has started
        if event.start_date and timezone.now() >= event.start_date:
            raise serializers.ValidationError({
                'event': 'Cannot create refunds after event has started'
            })
        
        # Validate event payment amount
        if event_payment_amount > 0 and event_payment:
            if event_payment_amount > event_payment.amount:
                raise serializers.ValidationError({
                    'event_payment_amount': f'Refund amount (£{event_payment_amount}) cannot exceed original payment (£{event_payment.amount})'
                })
        
        # Calculate total if not provided
        total = event_payment_amount + product_payment_amount
        if total <= 0:
            raise serializers.ValidationError({
                'total_refund_amount': 'Total refund amount must be greater than 0'
            })
        
        # Override total with calculated value
        data['total_refund_amount'] = total
        
        return data
    
    def create(self, validated_data):
        """Create refund with automatic field population"""
        request = self.context.get('request')
        participant = validated_data['participant']
        event = validated_data['event']
        
        # Set user who initiated the refund
        if request and request.user:
            validated_data['removed_by'] = request.user
        
        # Cache participant contact info if not provided
        if not validated_data.get('participant_email') and participant.user:
            if hasattr(participant.user, 'community') and participant.user.community:
                validated_data['participant_email'] = participant.user.community.contact_email or participant.user.email
                validated_data['participant_name'] = f"{participant.user.community.first_name} {participant.user.community.last_name}"
        
        # Determine refund contact email if not provided
        if not validated_data.get('refund_contact_email'):
            refund_contact_email = None
            
            # Check if event payment has a method with refund contact
            if validated_data.get('event_payment') and validated_data['event_payment'].method:
                refund_contact_email = validated_data['event_payment'].method.refund_contact_email
            
            # If no email from payment method, look for secretariat members
            if not refund_contact_email:
                secretariat_role = EventRole.objects.filter(
                    role_name=EventRole.EventRoleTypes.SECRETARIAT
                ).first()
                
                if secretariat_role:
                    secretariat_member = EventServiceTeamMember.objects.filter(
                        event=event,
                        roles=secretariat_role
                    ).select_related('user').first()
                    
                    if secretariat_member and secretariat_member.user:
                        refund_contact_email = secretariat_member.user.email
            
            # Fallback to event creator
            if not refund_contact_email and event.created_by:
                refund_contact_email = event.created_by.email
            
            validated_data['refund_contact_email'] = refund_contact_email or 'admin@example.com'
        
        # Determine if refund can be automatic
        if validated_data.get('event_payment') and validated_data['event_payment'].method:
            payment_method = validated_data['event_payment'].method
            if not validated_data.get('is_automatic_refund'):
                validated_data['is_automatic_refund'] = payment_method.supports_automatic_refunds
            if not validated_data.get('original_payment_method'):
                validated_data['original_payment_method'] = payment_method.get_method_display()
        
        return super().create(validated_data)


class RefundSummarySerializer(serializers.Serializer):
    """
    Serializer for refund summary statistics per event.
    """
    total_refunds = serializers.IntegerField()
    pending_refunds = serializers.IntegerField()
    in_progress_refunds = serializers.IntegerField()
    processed_refunds = serializers.IntegerField()
    failed_refunds = serializers.IntegerField()
    cancelled_refunds = serializers.IntegerField()
    total_refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    pending_refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    processed_refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    automatic_refunds = serializers.IntegerField()
    manual_refunds = serializers.IntegerField()
    average_processing_days = serializers.FloatField()
    currency = serializers.CharField(default='gbp')
