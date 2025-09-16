from rest_framework import filters, response
from rest_framework.decorators import action
from rest_framework import viewsets, permissions

from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from django.utils import timezone

from .serializers import *
from apps.events.api.serializers import SimplifiedEventSerializer
from apps.events.models import Event
from apps.users.models import CommunityRole

class CommunityUserViewSet(viewsets.ModelViewSet):
    '''
    Viewset related to user management
    '''
    queryset = get_user_model().objects.all()
    serializer_class = CommunityUserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ministry', 'gender', 'is_active', 'is_staff', 'is_encoder']
    search_fields = ['first_name', 'last_name', 'email', 'member_id', 'username']
    ordering_fields = ['last_name', 'first_name', 'date_of_birth', 'uploaded_at']
    ordering = ['last_name', 'first_name']
    permission_classes = [] # TODO: must change to authenticated only + add object permissions
    lookup_field = "member_id"
    
    
    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):
            return SimplifiedCommunityUserSerializer
        
        user = self.request.user
        if not user.is_authenticated or not user.is_superuser:
            # anonymous users only see simplified, #! remember that if they are not a superuser/encoder then cannot view ANY user data
            return SimplifiedCommunityUserSerializer

        # if it's a detail view (retrieve/update) check if it's "me"
        if self.action in ['retrieve', 'update', 'partial_update']:
            obj = self.get_object()
            if obj == user or user.is_superuser:
                return CommunityUserSerializer  # full serializer for self
            return SimplifiedCommunityUserSerializer

        # TODO: ensure members cannot see ANY user data except their own
        # for listing others
        # if self.action == "list":
        #     return SimplifiedCommunityUserSerializer

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
        now = timezone.now()

        # All events where the user is involved (service team OR participant)
        events = Event.objects.filter(
            models.Q(service_team_members__user=user) |
            models.Q(participants__user=user)
        ).distinct()

        # Split into upcoming and past
        upcoming_events = events.filter(start_date__gte=now).order_by('start_date')
        past_events = events.filter(start_date__lt=now).order_by('-start_date')

        serializer_upcoming = SimplifiedEventSerializer(upcoming_events, many=True)
        serializer_past = SimplifiedEventSerializer(past_events, many=True)

        # Add 'time_left' field to each upcoming event
        upcoming_events_data = serializer_upcoming.data
        for idx, event in enumerate(upcoming_events):
            start_date = event.start_date
            delta = start_date - now
            days = delta.days
            seconds = delta.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            # Format as 'X days, Y hours, Z minutes'
            time_left = f"{days} days, {hours} hours, {minutes} minutes" if days >= 0 else "Started"
            upcoming_events_data[idx]["time_left"] = time_left

        return response.Response({
            "upcoming_events": upcoming_events_data,
            "past_events": serializer_past.data
        })
        
class CommunityRoleViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing community roles
    '''
    queryset = CommunityRole.objects.all()
    serializer_class = CommunityRoleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_core']
    search_fields = ['role_name', 'role_description']

class UserCommunityRoleViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing user-community roles
    '''
    queryset = UserCommunityRole.objects.all()
    serializer_class = UserCommunityRoleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'role', 'is_active']

class AlergiesViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing allergies
    '''
    queryset = Allergy.objects.all().order_by("name")
    serializer_class = AllergySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MedicalConditionsViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing medical conditions
    '''
    queryset = MedicalCondition.objects.all().order_by("name")
    serializer_class = MedicalConditionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EmergencyContactViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing emergency contacts
    '''
    queryset = EmergencyContact.objects.all().select_related("user")
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]

