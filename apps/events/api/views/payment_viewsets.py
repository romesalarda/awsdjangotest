from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.events.models import EventPaymentMethod, EventPaymentPackage, EventPayment
from apps.events.api.serializers import (
    EventPaymentMethodSerializer,
    EventPaymentPackageSerializer,
    EventPaymentSerializer,
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
        payment = self.get_object()
        
        if payment.verified:
            return Response({
                "status": "already verified",
                "message": "This payment has already been verified."
            }, status=status.HTTP_200_OK)
        
        # Update payment status
        payment.verified = True
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
        return Response({
            "status": "payment verified",
            "message": f"Payment for participant {participant.event_pax_id} has been verified. Confirmation email sent to user.",
            "payment": serializer.data
        }, status=status.HTTP_200_OK)
