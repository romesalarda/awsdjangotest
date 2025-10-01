from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop
)
from apps.events.api.serializers import *
from apps.users.api.serializers import CommunityUserSerializer
from apps.events.api.filters import EventFilter
from apps.shop.api.serializers import EventProductSerializer, EventCartSerializer
from apps.shop.models import EventCart
from core.permissions import IsEncoderPermission
from apps.shop.api.serializers import EventCartMinimalSerializer

#! Remember that service team members are also participants but not all participants are service team members

# TODO: work on extra questions view, add extra description to each questions

class EventViewSet(viewsets.ModelViewSet):
    '''
    Viewset for CRUD operations with all types of events in the community
    '''
    
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EventFilter
    # filterset_fields = ['event_type', 'area_type', 'specific_area', 'name']
    search_fields = ['name', 'theme']
    ordering_fields = ['start_date', 'end_date', 'name', 'number_of_pax']
    ordering = ['-start_date']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        # if params 'detailed' in request query params, return detailed serializer
        if self.action in ['list', 'retrieve']:
            detailed = self.request.query_params.get('detailed', 'false').lower() == 'true'
            if detailed:
                return EventSerializer
            else:
                return SimplifiedEventSerializer
        return super().get_serializer_class()
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Event.objects.all()       
        # returns events that are specific to the user, created_by, supervisor, participant, service team member
        if user.is_authenticated and user.is_encoder:
            return Event.objects.filter(
                models.Q(created_by=user),
                is_public=True
            ).distinct()
        # for normal authenticated users, only show public events
        return Event.objects.filter(is_public=True)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        user = request.user
        if user.is_authenticated:
            participant = EventParticipant.objects.filter(event=instance, user=user).first()
            
            if not participant and not user.has_perm('events.view_event'):
                return Response(
                    {'error': _('You do not have permission to view this event.')},
                    status=status.HTTP_403_FORBIDDEN
                )
            elif participant and not participant.event.is_public:
                return Response(
                    {'error': _('You do not have permission to view this event.')}, 
                    status=status.HTTP_403_FORBIDDEN
                    )
            data['is_participant'] = bool(participant)
        return Response(data)
        
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        super().perform_create(serializer)
        
    @action(detail=True, methods=['get'], url_name="booking", url_path="booking")
    def booking(self, request, pk=None):
        '''
        Handle event booking logic here.
        '''
        # Manual booking details
        data = {           
            "event": {},
            "registration": {},
            "user": {},
            "merch": [],
            "resources": [],
            "questions": []
        }
        
        user = request.user
        if not user.is_authenticated:
            return Response(
                {'error': _('Authentication credentials were not provided.')},
                status=status.HTTP_401_UNAUTHORIZED
            )
        self.check_object_permissions(request, self.get_object())
        self.check_permissions(request)
        
        #! handle event details first
        event = self.get_object()
        serializer = EventSerializer(event)
        event_data = serializer.data
        basic_info = event_data.pop("basic_info", {})
        basic_info.pop("auto_approve_participants", None)
        basic_info.pop("status", None)
        event_dates = event_data.pop("dates", [])
        event_venue = event_data.pop("venue", {})
        event_people = event_data.pop("people", {})
        event_data.pop("payment_packages")
        event_data.pop("payment_methods")
        payment_deadline = event_dates.get("payment_deadline", None)

        basic_info.update({
            "dates": event_dates,
            "locations": [
                {
                    "name": location.get("name", ""), 
                    "address": self.get_full_address(location),
                    "venue_type": location.get("venue_type", "")
                } 
                for location in event_venue.pop("venues", [])
                ],
            "areas_involved": [area['area_name'] for area in event_venue.get("areas_involved", [])],
            "organiser_info": event_people.get("organisers", []),
        })
        data['event'] = basic_info
        
        #! registration info
        event_participant = EventParticipant.objects.filter(event=event, user=user).first()
        if not event_participant:
            return Response(
                {'error': _('You are not registered for this event.')},
                status=status.HTTP_403_FORBIDDEN
            )
        participant_serializer = EventParticipantSerializer(event_participant)
        
        register_data = participant_serializer.data

        health_info = register_data.pop("health", {})
        medical_info = health_info.get("medical_conditions", [])
        allergies = health_info.get("allergies", [])
        
        event_payments = register_data.pop("event_payments", [])
        # get most recent payment
        payment_details = event_payments[0] if event_payments else {}
        payment_details.pop("user", None)
        payment_details.pop("event", None)
        payment_details.pop("event_name", None)
        payment_details.pop("participant_details", None)
        payment_details.pop("id", None)
        payment_details.pop("status", None)
        payment_details.pop("package", None)
        payment_details.pop("stripe_payment_intent", None)
        method_id = payment_details.pop("method", None)
        payment_details.pop("amount", None)
        payment_details.pop("participant_user_email", None)
                
        if method_id and not payment_details.get("verified", False):
            payment_details["method_info"] = EventPaymentMethod.objects.filter(id=method_id).values().first()
        else:
            payment_details["method_info"] = None
            
        payment_details["payment_deadline"] = payment_deadline
        
        # extra_questions = event_data.pop("extra_questions", [])

        question_answers = QuestionAnswer.objects.filter(participant=event_participant).prefetch_related("selected_choices")
        question_answer_serializer = QuestionAnswerSerializer(question_answers, many=True)
        answers_data = question_answer_serializer.data

        registration_data = {
            "confirmation_number": register_data.pop("event_user_id"),
            "status": register_data.pop("status", {}).get("code", "500 ERROR"),
            "type": register_data.pop("participant_type", {}).get("code", "PARTICIPANT"),
            "dates": register_data.pop("dates", {}),
            "consents": register_data.pop("consents", {}),
            # flatten
            # "medical_conditions": [condition.get('name', '') for condition in medical_info],
            "emergency_contacts": [self.filter_emergency_contact(contact) for contact in register_data.pop("emergency_contacts", [])],
            # "allergies": [condition.get('name', '') for condition in allergies],
            "medical_conditions": medical_info,
            "allergies": allergies,
            # only pick the most recent to show
            "payment_details": payment_details,
            "questions": answers_data,
            "verified": payment_details.get("verified", False)
        }
        
        
        data["registration"] = registration_data
        
        #! user info
        user_serializer = SimplifiedCommunityUserSerializer(user)
        user_data = user_serializer.data
        user_data["primary_email"] = user.primary_email
        data["user"] = user_data
        
        #! Handle merch
        carts = EventCart.objects.filter(user=user, event=event)
        cart_serializer = EventCartMinimalSerializer(carts, many=True)
        data["merch"] = cart_serializer.data        
         #! resources
        resources = event_data.pop("resources", [])
        data["resources"] = resources
        #! questions

        participant_questions = ParticipantQuestion.objects.filter(participant=event_participant, event=event)
        participant_question_serializer = ParticipantQuestionSerializer(participant_questions, many=True)
        
        data["questions"] = [self.filter_question(q) for q in participant_question_serializer.data]

        return Response(data, status=status.HTTP_200_OK)
    
    @staticmethod
    def get_full_address(venue):
        address_parts = [
            venue.get('address_line_1', ''),
            venue.get('address_line_2', ''),
            venue.get('address_line_3', ''),
            venue.get('postcode', ''),
            venue.get('country', '')
        ]
        return ', '.join(part for part in address_parts if part)
    
    @staticmethod
    def filter_emergency_contact(contact):
        contact.pop("id", None)
        contact.pop("contact_relationship", None)
        relation = contact.pop("contact_relationship_display", None)
        contact["relation"] = relation
        return contact
    
    @staticmethod
    def filter_question(question):
        question.pop("admin_notes", None)
        question.pop("priority", None)
        question.pop("questions_type", None)
        question.pop("status", None)
        question.pop("participant_details", None)
        question.pop("participant", None)
        question.pop("event", None)
        return question
    
    # TODO: create a view that returns events that the user is involved in
    @action(detail=False, methods=['get'], url_name="my-events", url_path="my-events")
    def my_events(self, request):
        '''
        Retrieve a list of events that the user is involved in (created, supervisor, participant, service team member).
        '''
        simple = request.query_params.get('simple', 'true').lower() == 'true'
        user = request.user
        if not user.is_authenticated:
            return Response(
                {'error': _('Authentication credentials were not provided.')},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        events = Event.objects.filter(
            models.Q(created_by=user) |
            # models.Q(supervisors=user) |
            models.Q(participants__user=user) |
            models.Q(service_team_members__user=user)
        ).distinct()
        
        page = self.paginate_queryset(events)
        if page is not None:
            if simple:
                serializer = UserAwareEventSerializer(page, many=True, context={'request': request})
            else:
                serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        if simple:
            serializer = UserAwareEventSerializer(events, many=True, context={'request': request})
        else:
            serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)
    
    # participant related actions
    @action(detail=True, methods=['get'])
    def participants(self, request, pk=None):
        '''
        Retrieve a list of participants for a specific event.
        '''
        event = self.get_object()
        participants = event.participants.all()
        page = self.paginate_queryset(participants)
        if page is not None:
            serializer = SimplifiedEventParticipantSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = SimplifiedEventParticipantSerializer(participants, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="register", url_path="register")
    def register(self, request, pk=None):
        '''
        Register a user for a specific event.
        '''
        event = self.get_object()
        user = request.user
        self.check_object_permissions(request, event) # Ensure user has permission to register
        self.check_permissions(request) # Ensure user is authenticated
        
        if EventParticipant.objects.filter(event=event, user=user).exists():
            return Response(
                {'error': _('You are already registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        participant_type =  request.data.get('participant_type', EventParticipant.ParticipantType.PARTICIPANT)
        if participant_type not in dict(EventParticipant.ParticipantType.choices):
            return Response(
                {'error': _('Invalid participant type.')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if participant_type == EventParticipant.ParticipantType.SERVICE_TEAM:
            # generally service team registration should not be done this way
            # only event organizers/admins should be able to register themselves as ST
            if user.has_perm('events.add_eventserviceteammember'):
                service_team, created = EventServiceTeamMember.objects.get_or_create(event=event, user=user)
                if not created:
                    return Response(
                        {'error': _('You are already registered as a service team member for this event.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                service_team.roles.set(request.data.get('role_ids', []))
                return Response(
                    {'message': _('Successfully registered as a service team member.')},
                    status=status.HTTP_201_CREATED
                ) 
            else:
                return Response(
                    {'error': _('Service team registration is not allowed via this endpoint.')},
                    status=status.HTTP_400_BAD_REQUEST
                ) 
            
        participant = EventParticipant.objects.create(
            event=event,
            user=user,
            status=EventParticipant.ParticipantStatus.REGISTERED,
            participant_type=participant_type
        )
        
        serializer = SimplifiedEventParticipantSerializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name="remove-participant", url_path="remove-participant")
    def remove_participant(self, request, pk=None):
        '''
        Remove a participant from the event.
        '''
        event = self.get_object()
        user = request.user
        self.check_object_permissions(request, event)  # Ensure user has permission to remove
        try:
            participant = EventParticipant.objects.get(event=event, user=user)
        except EventParticipant.DoesNotExist:
            return Response(
                {'error': _('You are not registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        participant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'], url_name="attendance", url_path="attendance")
    def attendance(self, request, pk=None):
        '''
        Retrieve a list of attendance records for a specific event.
        '''
        event = self.get_object()
        attendance_records = event.attendance_records.all()
        page = self.paginate_queryset(attendance_records)
        if page is not None:
            serializer = EventDayAttendanceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventDayAttendanceSerializer(attendance_records, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path="service-team")
    def service_team(self, request, pk=None):
        '''
        Retrieve a list of service team members for a specific event.
        '''
        event = self.get_object()
        service_team = event.service_team_members.all()
        page = self.paginate_queryset(service_team)
        if page is not None:
            serializer = EventServiceTeamMemberSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventServiceTeamMemberSerializer(service_team, many=True)
        return Response(serializer.data)
    
    # service team related actions
    
    @action(detail=True, methods=['post'], url_name="add-service-member", url_path="add-service-member")
    def add_service_member(self, request, pk=None):
        '''
        Add a service team member to a specific event.
        {"member_id": "member-uuid", "role_ids": [role_uuid1, role_uuid2], "head_of_role": true}
        '''
        event = self.get_object()
        member_id = request.data.get('member_id')
        role_ids = request.data.get('role_ids', [])
        
        self.check_object_permissions(request, event) 
        self.check_permissions(request) 
        
        if not member_id:
            return Response(
                {'error': _('Member ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # avoid using real uuid, use member_id instead
            user = get_user_model().objects.get(member_id=member_id)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if EventServiceTeamMember.objects.filter(youth_camp=event, user=user).exists():
            return Response(
                {'error': _('User is already a service team member for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service_member = EventServiceTeamMember.objects.create(
            event=event,
            user=user,
            head_of_role=request.data.get('head_of_role', False)
        )
        
        if role_ids:
            roles = EventRole.objects.filter(id__in=role_ids)
            service_member.roles.set(roles)
        
        serializer = EventServiceTeamMemberSerializer(service_member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name="remove-service-member", url_path="remove-service-member")
    def remove_service_member(self, request, pk=None):
        '''
        Remove a service team member from a specific event.
        {"member_id": "member-uuid"}
        '''
        event = self.get_object()
        member_id = request.data.get('member_id')
        
        self.check_object_permissions(request, event) 
        self.check_permissions(request) 
        
        if not member_id:
            return Response(
                {'error': _('Member ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = get_user_model().objects.get(member_id=member_id)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            service_member = EventServiceTeamMember.objects.get(event=event, user=user)
        except EventServiceTeamMember.DoesNotExist:
            return Response(
                {'error': _('User is not a service team member for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        service_member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    # metadata related actions
    
    @action(detail=True, methods=['get'])
    def talks(self, request, pk=None):
        '''
        Retrieve a list of talks for a specific event.
        '''
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
        '''
        Retrieve a list of workshops for a specific event.
        '''
        event = self.get_object()
        workshops = event.workshops.all()
        page = self.paginate_queryset(workshops)
        if page is not None:
            serializer = EventWorkshopSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventWorkshopSerializer(workshops, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name="resources", url_path="resources")
    def resources(self, request, pk=None):
        '''
        Retrieve a list of resources for a specific event.
        '''
        event = self.get_object()
        resources = event.resources.all()
        page = self.paginate_queryset(resources)
        if page is not None:
            serializer = PublicEventResourceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PublicEventResourceSerializer(resources, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_name="products", url_path="products")
    def products(self, request, pk=None):
        '''
        Retrieve a list of products for a specific event.
        '''
        event = self.get_object()
        products = event.products.all()
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = EventProductSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = EventProductSerializer(products, many=True)
        return Response(serializer.data)

class EventServiceTeamMemberViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event service team members.
    '''
    queryset = EventServiceTeamMember.objects.all()
    serializer_class = EventServiceTeamMemberSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['youth_camp', 'user', 'head_of_role']

class EventRoleViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event roles.
    '''
    queryset = EventRole.objects.all()
    serializer_class = EventRoleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['role_name', 'description']

class EventParticipantViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event participants.
    Different from users/api/views.py -> CommunityUserViewSet -> events action
    '''
    queryset = EventParticipant.objects.all()
    serializer_class = EventParticipantSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['event', 'user', 'status', 'participant_type']
    search_fields = ['user__first_name', 'user__last_name', 'team_assignment']
    lookup_field = "event_pax_id"
    
    #! remember to handle how service are register, can anyone just register as a participant?
    #! or should it be only event organizers/admins who can add participants?
        
    @action(detail=False, methods=['post'], url_name="register", url_path="register")
    def register(self, request):
        '''
        {"user": uuid, "event": uuid, "participant_type": "PARTICIPANT"}
        Allow any to register for an event as a participant mainly. Service team registration should be handled separately.
        '''
        user = request.user
        event_id = request.data.get('event_id')
        participant_type = request.data.get('participant_type', EventParticipant.ParticipantType.PARTICIPANT)
        
        if not event_id:
            return Response(
                {'error': _('Event ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response(
                {'error': _('Event not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if EventParticipant.objects.filter(event=event, user=user).exists():
            return Response(
                {'error': _('You are already registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if participant_type not in dict(EventParticipant.ParticipantType.choices):
            return Response(
                {'error': _('Invalid participant type.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        if participant_type == EventParticipant.ParticipantType.SERVICE_TEAM and not user.has_perm('events.add_eventserviceteammember'):
            return Response(
                {'error': _('Service team registration is not allowed via this endpoint.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        participant = EventParticipant.objects.create(
            event=event,
            user=user,
            status=EventParticipant.ParticipantStatus.REGISTERED,
            participant_type=participant_type
        )
        
        serializer = self.get_serializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    #TODO: add role to a service team member AND NOT a participant
    #TODO: cancel booking
    
    
    @action(detail=True, methods=['post'], url_name="mark-attended", url_path="mark-attended")
    def mark_attended(self, request, event_pax_id=None):
        # TODO: only allow event organizers/admins to mark attendance
        participant = self.get_object()
        participant.status = EventParticipant.ParticipantStatus.ATTENDED
        participant.attended_date = timezone.now()
        participant.save()
        serializer = self.get_serializer(participant)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        # only return event code
        request = super().create(request, *args, **kwargs)
        data = request.data
        return Response({"event_user_id": data["event_user_id"]}, status=request.status_code)

class EventTalkViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event talks.
    '''
    queryset = EventTalk.objects.all()
    serializer_class = EventTalkSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'speaker', 'talk_type', 'is_published']
    ordering_fields = ['start_time', 'end_time']
    ordering = ['start_time']

class EventWorkshopViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event workshops.
    '''
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

class PublicEventResourceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing public event resources (memos, files, links).
    """
    queryset = EventResource.objects.all()
    serializer_class = PublicEventResourceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # anyone can GET, only logged-in can modify

class EventDayAttendanceViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event day attendance.
    '''
    queryset = EventDayAttendance.objects.select_related("event", "user")
    serializer_class = EventDayAttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["event", "user", "day_date", "day_id"]
    search_fields = ["user__first_name", "user__last_name", "event__name"]
    ordering_fields = ["day_date", "check_in_time", "check_out_time"]
    ordering = ["-check_in_time"]
    permission_classes = [permissions.IsAuthenticated]