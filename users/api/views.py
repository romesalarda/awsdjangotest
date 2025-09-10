from rest_framework import filters, response
from rest_framework.decorators import action
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from users.models import CommunityRole
from django.contrib.auth import get_user_model

from .serializers import *
from events.api.serializers import SimplifiedEventSerializer
from events.models import Event

class CommunityUserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all()
    serializer_class = CommunityUserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ministry', 'gender', 'is_active', 'is_staff', 'is_encoder']
    search_fields = ['first_name', 'last_name', 'email', 'member_id', 'username']
    ordering_fields = ['last_name', 'first_name', 'date_of_birth', 'uploaded_at']
    ordering = ['last_name', 'first_name']
    permission_classes = [permissions.AllowAny] # TODO: must change to authenticated only + add object permissions
    lookup_field = "member_id"
    
    def get_serializer_class(self):
        user = self.request.user
        if not user.is_authenticated:
            # anonymous users only see simplified
            return SimplifiedCommunityUserSerializer

        # if it's a detail view (retrieve/update) check if it's "me"
        if self.action in ['retrieve', 'update', 'partial_update']:
            obj = self.get_object()
            if obj == user or user.is_superuser:
                return CommunityUserSerializer  # full serializer for self
            return SimplifiedCommunityUserSerializer

        # for listing others
        if self.action == "list":
            return SimplifiedCommunityUserSerializer

        # fallback
        return CommunityUserSerializer
    
    @action(detail=True, methods=['get'])
    def roles(self, request, member_id=None):
        user = self.get_object()
        roles = user.role_links.all()
        serializer = UserCommunityRoleSerializer(roles, many=True)
        return response.Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def events(self, request, member_id=None):
        user = self.get_object()
        # Events where user is in service team
        service_events = Event.objects.filter(service_team_members__user=user)
        # Events where user is a participant
        participant_events = Event.objects.filter(participants__user=user)
        
        service_serializer = SimplifiedEventSerializer(service_events, many=True)
        participant_serializer = SimplifiedEventSerializer(participant_events, many=True)
        
        return response.Response({
            'service_team_events': service_serializer.data,
            'participant_events': participant_serializer.data
        })

class CommunityRoleViewSet(viewsets.ModelViewSet):
    queryset = CommunityRole.objects.all()
    serializer_class = CommunityRoleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_core']
    search_fields = ['role_name', 'role_description']

class UserCommunityRoleViewSet(viewsets.ModelViewSet):
    queryset = UserCommunityRole.objects.all()
    serializer_class = UserCommunityRoleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'role', 'is_active']

class AlergiesViewSet(viewsets.ModelViewSet):
    queryset = Allergy.objects.all().order_by("name")
    serializer_class = AllergySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MedicalConditionsViewSet(viewsets.ModelViewSet):
    queryset = MedicalCondition.objects.all().order_by("name")
    serializer_class = MedicalConditionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EmergencyContactViewSet(viewsets.ModelViewSet):
    queryset = EmergencyContact.objects.all().select_related("user")
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]
