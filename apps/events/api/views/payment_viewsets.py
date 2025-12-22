from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from apps.events.models import EventPaymentMethod, EventPaymentPackage, EventPayment, DonationPayment, EventParticipant
from apps.events.api.serializers import (
    EventPaymentMethodSerializer,
    EventPaymentPackageSerializer,
    EventPaymentSerializer,
    DonationPaymentSerializer,
    DonationPaymentListSerializer,
)
from apps.events.email_utils import send_payment_verification_email
import threading


class EventPaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = EventPaymentMethod.objects.all().order_by("-created_at")
    serializer_class = EventPaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EventPaymentPackageViewSet(viewsets.ModelViewSet):
    queryset = EventPaymentPackage.objects.all().order_by("-created_at")
    serializer_class = EventPaymentPackageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EventPaymentViewSet(viewsets.ModelViewSet):
    queryset = EventPayment.objects.all().order_by("-created_at")
    serializer_class = EventPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'], url_name='verify-payment', url_path='verify-payment', permission_classes=[permissions.IsAdminUser])
    def verify_payment(self, request, pk=None):
        """
        Admin action to verify/approve an event registration payment.
        Marks payment as verified, then sends confirmation email to participant.
        """
        payment: EventPayment = self.get_object()
        
        if payment.verified:
            return Response({
                "status": "already verified",
                "message": "This payment has already been verified."
            }, status=status.HTTP_200_OK)
        
        # Update payment status
        payment.verified = True
        payment.status = EventPayment.PaymentStatus.SUCCEEDED
        payment.save()
        
        # Send confirmation email in background
        participant = payment.participant
        def send_email():
            try:
                send_payment_verification_email(participant)
                print(f"📧 Registration payment verification email queued for {participant.event_pax_id}")
            except Exception as e:
                print(f"⚠️ Failed to send payment verification email: {e}")
        
        email_thread = threading.Thread(target=send_email)
        email_thread.start()
        
        serializer = self.get_serializer(payment)
        participant.status = EventParticipant.ParticipantStatus.CONFIRMED
        participant.verified = True
        participant.save()
        return Response({
            "status": "payment verified",
            "message": f"Payment for participant {participant.event_pax_id} has been verified. Confirmation email sent to user.",
            "payment": serializer.data
        }, status=status.HTTP_200_OK)


class DonationPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing donation payments.
    
    Provides full CRUD operations for donation payments with additional actions:
    - List all donations with filtering
    - Create new donations
    - Retrieve donation details
    - Update donation status
    - Delete donations (admin only)
    - Mark donations as paid
    - Verify donations
    - Get donation statistics
    
    Permissions:
    - Authenticated users can view and create donations
    - Admins can update and delete
    """
    queryset = DonationPayment.objects.all().select_related(
        'user__user', 'event', 'method'
    ).order_by("-created_at")
    serializer_class = DonationPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        Uses lightweight serializer for list view.
        """
        if self.action == 'list':
            return DonationPaymentListSerializer
        return DonationPaymentSerializer
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        
        Supported filters:
        - event: Filter by event ID
        - participant: Filter by participant ID
        - status: Filter by payment status
        - method: Filter by payment method ID
        - verified: Filter by verification status (true/false)
        - pay_to_event: Filter by pay_to_event status (true/false)
        - date_from: Filter donations created after this date
        - date_to: Filter donations created before this date
        """
        queryset = super().get_queryset()
        
        # Filter by event
        event_id = self.request.query_params.get('event')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        
        # Filter by participant
        participant_id = self.request.query_params.get('participant')
        if participant_id:
            queryset = queryset.filter(user_id=participant_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by payment method
        method_id = self.request.query_params.get('method')
        if method_id:
            queryset = queryset.filter(method_id=method_id)
        
        # Filter by verified status
        verified = self.request.query_params.get('verified')
        if verified is not None:
            queryset = queryset.filter(verified=verified.lower() == 'true')
        
        # Filter by pay_to_event status
        pay_to_event = self.request.query_params.get('pay_to_event')
        if pay_to_event is not None:
            queryset = queryset.filter(pay_to_event=pay_to_event.lower() == 'true')
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        return queryset
    
    @action(detail=True, methods=['post'], url_name='mark-paid', url_path='mark-paid', permission_classes=[permissions.IsAdminUser])
    def mark_paid(self, request, pk=None):
        """
        Admin action to mark a donation payment as paid/succeeded.
        
        Updates:
        - Status to SUCCEEDED
        - Sets paid_at timestamp
        
        Returns:
        - Updated donation payment data
        - Success message
        """
        donation = self.get_object()
        
        if donation.status == DonationPayment.PaymentStatus.SUCCEEDED:
            return Response({
                "status": "already paid",
                "message": "This donation has already been marked as paid."
            }, status=status.HTTP_200_OK)
        
        # Update donation status
        from django.utils import timezone
        donation.status = DonationPayment.PaymentStatus.SUCCEEDED
        donation.paid_at = timezone.now()
        donation.save()
        
        serializer = self.get_serializer(donation)
        return Response({
            "status": "donation marked as paid",
            "message": f"Donation {donation.event_payment_tracking_number or donation.id} has been marked as paid.",
            "donation": serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name='verify-donation', url_path='verify-donation', permission_classes=[permissions.IsAdminUser])
    def verify_donation(self, request, pk=None):
        """
        Admin action to verify/approve a donation payment.
        
        Updates:
        - Sets verified to True
        
        Returns:
        - Updated donation payment data
        - Success message
        """
        donation = self.get_object()
        
        if donation.verified:
            return Response({
                "status": "already verified",
                "message": "This donation has already been verified."
            }, status=status.HTTP_200_OK)
        
        # Update donation verification status
        donation.verified = True
        donation.save()
        
        serializer = self.get_serializer(donation)
        return Response({
            "status": "donation verified",
            "message": f"Donation {donation.event_payment_tracking_number or donation.id} has been verified.",
            "donation": serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_name='statistics', url_path='statistics')
    def statistics(self, request):
        """
        Get donation statistics.
        
        Returns:
        - Total donations count
        - Total amount donated (all currencies)
        - Amount by status
        - Amount by event
        - Recent donations
        
        Supports same filters as list action.
        """
        queryset = self.get_queryset()
        
        # Overall statistics
        total_count = queryset.count()
        total_amount = queryset.filter(
            status=DonationPayment.PaymentStatus.SUCCEEDED
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Statistics by status
        status_stats = []
        for status_choice in DonationPayment.PaymentStatus.choices:
            status_value = status_choice[0]
            status_label = status_choice[1]
            status_donations = queryset.filter(status=status_value)
            status_stats.append({
                "status": status_value,
                "status_label": status_label,
                "count": status_donations.count(),
                "total_amount": status_donations.aggregate(total=Sum('amount'))['total'] or 0
            })
        
        # Statistics by event
        event_stats = queryset.values(
            'event__id', 'event__name'
        ).annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-total_amount')[:10]
        
        # Recent donations
        recent_donations = DonationPaymentListSerializer(
            queryset[:5], 
            many=True, 
            context={'request': request}
        ).data
        
        return Response({
            "total_donations": total_count,
            "total_amount": float(total_amount),
            "currency": "GBP",
            "by_status": status_stats,
            "by_event": list(event_stats),
            "recent_donations": recent_donations
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_name='by-event', url_path='by-event/(?P<event_id>[^/.]+)')
    def by_event(self, request, event_id=None):
        """
        Get all donations for a specific event.
        
        Returns:
        - List of donations for the event
        - Event statistics
        """
        donations = self.get_queryset().filter(event_id=event_id)
        
        serializer = DonationPaymentListSerializer(
            donations, 
            many=True, 
            context={'request': request}
        )
        
        # Event-specific statistics
        total_amount = donations.filter(
            status=DonationPayment.PaymentStatus.SUCCEEDED
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        return Response({
            "event_id": event_id,
            "total_donations": donations.count(),
            "total_amount": float(total_amount),
            "currency": "GBP",
            "donations": serializer.data
        }, status=status.HTTP_200_OK)
