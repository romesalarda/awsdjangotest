from rest_framework import viewsets, permissions
from events.models import EventPaymentMethod, EventPaymentPackage, EventPayment
from events.api.serializers import (
    EventPaymentMethodSerializer,
    EventPaymentPackageSerializer,
    EventPaymentSerializer,
)


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
