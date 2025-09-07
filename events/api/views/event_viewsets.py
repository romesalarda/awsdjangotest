from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop
)
from events.api.serializers import *
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from events.api.filters import EventFilter

# TODO: Add guest viewset

class EventViewSet(viewsets.ModelViewSet):
    '''
    Viewset for CRUD operations with all types of events in the community
    '''
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EventFilter
    # filterset_fields = ['event_type', 'area_type', 'specific_area', 'name']
    search_fields = ['name', 'theme', 'venue_name', 'venue_address']
    ordering_fields = ['start_date', 'end_date', 'name', 'number_of_pax']
    ordering = ['-start_date']
    
    @action(detail=True, methods=['get'])
    def participants(self, request, pk=None):
        event = self.get_object()
        participants = event.participants.all()
        page = self.paginate_queryset(participants)
        if page is not None:
            serializer = EventParticipantSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventParticipantSerializer(participants, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path="service-team")
    def service_team(self, request, pk=None):
        event = self.get_object()
        service_team = event.service_team_members.all()
        page = self.paginate_queryset(service_team)
        if page is not None:
            serializer = EventServiceTeamMemberSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventServiceTeamMemberSerializer(service_team, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def talks(self, request, pk=None):
        event = self.get_object()
        talks = event.talks.all()
        page = self.paginate_queryset(talks)
        if page is not None:
            serializer = EventTalkSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventTalkSerializer(talks, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def workshops(self, request, pk=None):
        event = self.get_object()
        workshops = event.workshops.all()
        page = self.paginate_queryset(workshops)
        if page is not None:
            serializer = EventWorkshopSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventWorkshopSerializer(workshops, many=True)
        return Response(serializer.data)

class EventServiceTeamMemberViewSet(viewsets.ModelViewSet):
    queryset = EventServiceTeamMember.objects.all()
    serializer_class = EventServiceTeamMemberSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['youth_camp', 'user', 'head_of_role']

class EventRoleViewSet(viewsets.ModelViewSet):
    queryset = EventRole.objects.all()
    serializer_class = EventRoleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['role_name', 'description']

class EventParticipantViewSet(viewsets.ModelViewSet):
    queryset = EventParticipant.objects.all()
    serializer_class = EventParticipantSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['event', 'user', 'status', 'participant_type']
    search_fields = ['user__first_name', 'user__last_name', 'team_assignment']
    
    @action(detail=True, methods=['post'])
    def mark_attended(self, request, pk=None):
        participant = self.get_object()
        participant.status = EventParticipant.ParticipantStatus.ATTENDED
        participant.attended_date = timezone.now()
        participant.save()
        serializer = self.get_serializer(participant)
        return Response(serializer.data)

class EventTalkViewSet(viewsets.ModelViewSet):
    queryset = EventTalk.objects.all()
    serializer_class = EventTalkSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'speaker', 'talk_type', 'is_published']
    ordering_fields = ['start_time', 'end_time']
    ordering = ['start_time']

class EventWorkshopViewSet(viewsets.ModelViewSet):
    queryset = EventWorkshop.objects.all()
    serializer_class = EventWorkshopSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'primary_facilitator', 'level', 'is_published', 'is_full']
    ordering_fields = ['start_time', 'end_time', 'max_participants']
    ordering = ['start_time']
    
    @action(detail=True, methods=['post'])
    def add_facilitator(self, request, pk=None):
        workshop = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            user = get_user_model().objects.get(id=user_id)
            workshop.facilitators.add(user)
            workshop.save()
            serializer = self.get_serializer(workshop)
            return Response(serializer.data)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found')},
                status=status.HTTP_404_NOT_FOUND
            )
            
# ! deprecated
# class GuestParticipantViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint to create, update, delete, and list guest participants.
#     """
#     queryset = GuestParticipant.objects.all()
#     serializer_class = GuestParticipantSerializer
#     permission_classes = [permissions.IsAuthenticated]  # adjust as needed


class PublicEventResourceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing public event resources (memos, files, links).
    """
    queryset = PublicEventResource.objects.all()
    serializer_class = PublicEventResourceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # anyone can GET, only logged-in can modify