from rest_framework import generics, permissions, filters
from rest_framework.decorators import action
from .serializers import *
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from users.models import CommunityRole
from django.contrib.auth import get_user_model

class CommunityUserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all()
    serializer_class = CommunityUserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ministry', 'gender', 'is_active', 'is_staff', 'is_encoder']
    search_fields = ['first_name', 'last_name', 'email', 'member_id', 'username']
    ordering_fields = ['last_name', 'first_name', 'date_of_birth', 'uploaded_at']
    ordering = ['last_name', 'first_name']
    
    @action(detail=True, methods=['get'])
    def roles(self, request, pk=None):
        user = self.get_object()
        roles = user.role_links.all()
        serializer = UserCommunityRoleSerializer(roles, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        user = self.get_object()
        # Events where user is in service team
        service_events = Event.objects.filter(service_team_members__user=user)
        # Events where user is a participant
        participant_events = Event.objects.filter(participants__user=user)
        
        service_serializer = SimplifiedEventSerializer(service_events, many=True)
        participant_serializer = SimplifiedEventSerializer(participant_events, many=True)
        
        return Response({
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