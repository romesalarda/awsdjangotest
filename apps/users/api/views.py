from rest_framework import filters, response
from rest_framework.decorators import action
from rest_framework import viewsets, permissions, views

from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models

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
    permission_classes = [permissions.IsAuthenticated] 
    lookup_field = "member_id"
    
    # TODO: double check read permissions - only logged in user can see the data about themselves and NO ONE else. Superusers can see everything - override Retrieve method
        
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_name="self", url_path="me")
    def get_self(self, request):
        '''
        Get full user details about the current logged in user
        '''
        self.check_permissions(request)        
        serializer = CommunityUserSerializer(request.user)
        return response.Response(serializer.data)
    
    
    def get_serializer_class(self):
        # signed in users can only view full data about themselves
        if getattr(self, 'swagger_fake_view', False):
            return SimplifiedCommunityUserSerializer
        
        user = self.request.user
        if not user.is_authenticated or not user.is_superuser:
            return SimplifiedCommunityUserSerializer

        if self.action in ['retrieve', 'update', 'partial_update']:
            obj = self.get_object()
            if obj == user or user.is_superuser:
                return CommunityUserSerializer 
            return SimplifiedCommunityUserSerializer
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

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_name="search", url_path="search")
    def search_users(self, request):
        '''
        Search users by name, email, member_id, with location filtering
        For use in user selection dropdowns and autocomplete
        '''
        query = request.query_params.get('q', '').strip()
        area_id = request.query_params.get('area_id', None)
        ministry = request.query_params.get('ministry', None)
        limit = int(request.query_params.get('limit', 20))
        
        if not query:
            return response.Response([])
        
        queryset = get_user_model().objects.filter(is_active=True)
        
        # Text search across multiple fields
        queryset = queryset.filter(
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(preferred_name__icontains=query) |
            models.Q(primary_email__icontains=query) |
            models.Q(secondary_email__icontains=query) |
            models.Q(member_id__icontains=query) |
            models.Q(username__icontains=query)
        )
        
        # Optional filters
        if area_id:
            queryset = queryset.filter(area_from_id=area_id)
        
        if ministry:
            queryset = queryset.filter(ministry=ministry)
        
        # Order by relevance (exact matches first, then partial)
        queryset = queryset.order_by('last_name', 'first_name')[:limit]
        
        # Use simplified serializer for search results
        serializer = SimplifiedCommunityUserSerializer(queryset, many=True)
        return response.Response(serializer.data)
        
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

class CurrentUserView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = CommunityUserSerializer(request.user)
        return response.Response(serializer.data)