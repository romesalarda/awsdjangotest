import uuid
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from rest_framework import serializers

from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventPayment
)

from apps.events.api.serializers import *
from apps.events.api.serializers.event_serializers import ParticipantManagementSerializer
from apps.users.api.serializers import CommunityUserSerializer
from apps.events.api.filters import EventFilter
from apps.shop.api.serializers import EventProductSerializer, EventCartSerializer
from apps.shop.models import EventCart, ProductPayment, EventProduct, EventProductOrder, ProductSize
from apps.shop.api.serializers import EventCartMinimalSerializer
from apps.shop.api.serializers.payment_serializers import ProductPaymentMethodSerializer
from apps.events.websocket_utils import websocket_notifier, serialize_participant_for_websocket, get_event_supervisors
from apps.events.email_utils import send_booking_confirmation_email, send_payment_verification_email
from apps.shop.email_utils import send_payment_verified_email, send_order_update_email
import threading

#! Remember that service team members are also participants but not all participants are service team members

def test_safe_uuid(obj):
    try:
        obj = uuid.UUID(obj)
        return True
    except ValueError:
        return False

class EventViewSet(viewsets.ModelViewSet):
    '''
    Viewset for CRUD operations with all types of events in the community
    '''
    
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    lookup_field = 'id'  # Use UUID id field for lookups
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
        print(f"🔧 DEBUG get_queryset - user: {user}, is_superuser: {user.is_superuser}, is_encoder: {getattr(user, 'is_encoder', False)}")
        
        if user.is_superuser:
            queryset = Event.objects.all()
            print(f"🔧 DEBUG get_queryset - superuser queryset count: {queryset.count()}")
            return queryset
        
        if user.is_authenticated and user.is_encoder:
            # Encoder users can access events they created OR public events
            queryset = Event.objects.filter(
                Q(created_by=user) | Q(is_public=True)
            ).distinct()
            print(f"🔧 DEBUG get_queryset - encoder queryset count: {queryset.count()}")
            # print(f"🔧 DEBUG get_queryset - encoder queryset SQL: {queryset.query}")
            return queryset
        
        # For normal authenticated users, only show public events
        queryset = Event.objects.filter(is_public=True)
        print(f"🔧 DEBUG get_queryset - regular user queryset count: {queryset.count()}")
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        user = request.user
        if user.is_authenticated:
            participant = EventParticipant.objects.filter(event=instance, user=user).first()
            data['is_participant'] = bool(participant)
            data['participant_count'] = EventParticipant.objects.filter(event=instance).count()

        return Response(data)
        
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        super().perform_create(serializer)
        
    @action(detail=True, methods=['get', 'post', 'delete'], url_name="service_team", url_path="service-team")
    def manage_service_team(self, request, id=None):
        '''
        Manage service team members for an event
        GET: List all service team members
        POST: Add a new service team member
        DELETE: Remove a service team member
        '''
        event = self.get_object()
        
        if request.method == 'GET':
            # Return all service team members with their roles
            service_team = EventServiceTeamMember.objects.filter(event=event).select_related('user').prefetch_related('roles')
            serializer = EventServiceTeamMemberSerializer(service_team, many=True)
            return Response(serializer.data)
            
        elif request.method == 'POST':
            # Add new service team member
            user_id = request.data.get('user_id')
            role_ids = request.data.get('role_ids', [])
            head_of_role = request.data.get('head_of_role', False)
            
            if not user_id:
                return Response(
                    {'error': 'user_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user = get_user_model().objects.get(id=user_id)
                
                # Check if user is already in service team
                if EventServiceTeamMember.objects.filter(event=event, user=user).exists():
                    return Response(
                        {'error': 'User is already in the service team for this event'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Create service team member
                service_member = EventServiceTeamMember.objects.create(
                    event=event,
                    user=user,
                    head_of_role=head_of_role,
                    assigned_by=request.user
                )
                
                # Add roles if provided
                if role_ids:
                    roles = EventRole.objects.filter(id__in=role_ids)
                    service_member.roles.set(roles)
                
                serializer = EventServiceTeamMemberSerializer(service_member)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
                
            except get_user_model().DoesNotExist:
                return Response(
                    {'error': 'User not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {'error': str(e)}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        elif request.method == 'DELETE':
            # Remove service team member
            user_id = request.data.get('user_id')
            if not user_id:
                return Response(
                    {'error': 'user_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                service_member = EventServiceTeamMember.objects.get(event=event, user_id=user_id)
                service_member.delete()
                return Response(
                    {'message': 'Service team member removed successfully'}, 
                    status=status.HTTP_200_OK
                )
            except EventServiceTeamMember.DoesNotExist:
                return Response(
                    {'error': 'Service team member not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

    @action(detail=True, methods=['patch'], url_name="update_service_member", url_path="service-team/(?P<member_id>[^/.]+)")
    def update_service_member(self, request, id=None, member_id=None):
        '''
        Update a specific service team member's roles or head_of_role status
        '''
        event = self.get_object()
        
        try:
            service_member = EventServiceTeamMember.objects.get(event=event, id=member_id)
            
            # Update fields if provided
            if 'head_of_role' in request.data:
                service_member.head_of_role = request.data['head_of_role']
                service_member.save()
            
            if 'role_ids' in request.data:
                roles = EventRole.objects.filter(id__in=request.data['role_ids'])
                service_member.roles.set(roles)
            
            serializer = EventServiceTeamMemberSerializer(service_member)
            return Response(serializer.data)
            
        except EventServiceTeamMember.DoesNotExist:
            return Response(
                {'error': 'Service team member not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'], url_name="roles", url_path="roles")
    def get_event_roles(self, request):
        '''
        Get all available event roles for selection
        '''
        roles = EventRole.objects.all().order_by('role_name')
        serializer = EventRoleSerializer(roles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_name="booking", url_path="booking")
    def booking(self, request, id=None):
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
        print("User:", user)
        self.check_object_permissions(request, self.get_object())
        self.check_permissions(request)
        # print("Permissions checked")
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
        # payment_details["bank_reference"] = 
        # print()
        
        # print("❗ payment_details:", payment_details)
        
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
        # show only carts relating to that event, and also show carts that are created by admin 
        carts = EventCart.objects.filter(user=user, event=event).exclude(active=True, created_via_admin=False) 
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
    def participants(self, request, pk=None, id=None):
        '''
        Retrieve a list of participants for a specific event.
        
        Supports filtering and ordering:
        - ?area=chapter/area/cluster_<id> (filter by area, chapter, or cluster)
        - ?bank_reference= (filter by bank reference in payments)
        - ?outstanding_payments=true/false (filter by payment status)
        - ?identity= (filter by name, email, or phone)
        - ?status= (filter by participant status)
        - ?order_by=recent_updates (order by most recent activity)
        - ?search= (general search across multiple fields)
        '''
        # Handle both pk and id parameters from DRF routing
        event_lookup = id if id is not None else pk
        print(f"🚀 Using event lookup: {event_lookup} (pk={pk}, id={id})")
        print(f"� PARTICIPANTS METHOD CALLED - pk: {pk}, query_params: {dict(request.query_params)}")
        print(f"�🔍 DEBUG participants - pk parameter: {pk}")
        print(f"🔍 DEBUG participants - request user: {request.user}")
        print(f"🔍 DEBUG participants - user is_superuser: {request.user.is_superuser}")
        print(f"🔍 DEBUG participants - user is_encoder: {getattr(request.user, 'is_encoder', False)}")
        

        queryset = self.get_queryset()
        print(f"🔍 DEBUG participants - queryset count: {queryset.count()}")
        # print(f"🔍 DEBUG participants - queryset SQL: {queryset.query}")
        
        # Debug: Check the raw Event count vs queryset count
        all_events_count = Event.objects.all().count()
        print(f"🔍 DEBUG participants - total events in DB: {all_events_count}")
        
        # Debug: Check if there are duplicate events with the same id
        if event_lookup:
            matching_events = queryset.filter(id=event_lookup)
            print(f"🔍 Events matching id '{event_lookup}': {matching_events.count()}")
            
            # Also check all events with this ID in the entire database
            all_matching = Event.objects.filter(id=event_lookup)
            print(f"🔍 ALL events in DB with id '{event_lookup}': {all_matching.count()}")
            
            if matching_events.count() > 1:
                print(f"⚠️ WARNING: Multiple events found with id '{event_lookup}' in filtered queryset")
                for i, event in enumerate(matching_events):
                    print(f"   - Event {i+1}: {event.name} (id: {event.id})")
                    
            if all_matching.count() > 1:
                print(f"⚠️ WARNING: Multiple events found with id '{event_lookup}' in ENTIRE database")
                for i, event in enumerate(all_matching):
                    print(f"   - DB Event {i+1}: {event.name} (id: {event.id})")
        print("⚠️ Query parameters:", dict(request.query_params))
        # Get event object directly instead of using self.get_object() which seems to have issues with query params
        try:
            print(f"🔍 DEBUG participants - About to get event directly using event_lookup: {event_lookup}")
            event = queryset.get(id=event_lookup)
            print(f"🔍 DEBUG participants - Successfully retrieved event: {event.name} (id: {event.id})")
        except Event.MultipleObjectsReturned as e:
            # Handle the case where multiple events are returned
            print(f"❌ ERROR: Multiple events returned for id '{event_lookup}': {str(e)}")
            matching_events = queryset.filter(id=event_lookup)
            print(f"   Total matching events in queryset: {matching_events.count()}")
            for i, evt in enumerate(matching_events):
                print(f"   Event {i+1}: {evt.name} (id: {evt.id})")
            # Use the first event as a fallback
            event = matching_events.first()
            print(f"   Using first event: {event.name} (id: {event.id})")
        except Event.DoesNotExist as e:
            print(f"❌ ERROR: Event not found for id '{event_lookup}': {str(e)}")
            return Response({'error': 'Event not found'}, status=404)
        except Exception as unexpected_error:
            print(f"❌ UNEXPECTED ERROR in get_object(): {unexpected_error}")
            print(f"❌ Error type: {type(unexpected_error)}")
            import traceback
            traceback.print_exc()
            return Response({'error': f'Unexpected error: {str(unexpected_error)}'}, status=500)
        
        simple = request.query_params.get('simple', 'true').lower() == 'true'
        order_by = request.query_params.get('order_by', 'registration_date')
        
        query_params = []
        
        # Enhanced search functionality
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__primary_email__icontains=search) |
                Q(user__phone_number__icontains=search) |
                Q(event_pax_id__icontains=search_upper) |
                Q(participant_event_payments__bank_reference__icontains=search_upper) |
                Q(user__product_payments__bank_reference__icontains=search_upper)
            )
        
        # Identity filter (exact or partial match)
        identity = request.query_params.get("identity")
        if identity:
            identity_upper = identity.upper()
            query_params.append(
                Q(user__first_name__icontains=identity) |
                Q(user__last_name__icontains=identity) |
                Q(user__primary_email__icontains=identity) |
                Q(user__phone_number__icontains=identity) |
                Q(event_pax_id__icontains=identity_upper)
            )
        
        # Area filtering - support multiple values
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__area_from__area_name__icontains=area) |
                        Q(user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
            
        # Chapter filtering - support multiple values
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    print(f"🔍 DEBUG participants - Applying chapter filter: '{chapter}'")
                    chapter_queries.append(Q(user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
            
        # Cluster filtering - support multiple values
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    print(f"🔍 DEBUG participants - Applying cluster filter: '{cluster}'")
                    cluster_queries.append(Q(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
            
        # Bank reference filter (for both event and product payments)
        # This handles bank_reference, event_payment_tracking_number, and payment_reference_id
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(participant_event_payments__bank_reference__icontains=bank_reference_upper) |
                Q(participant_event_payments__event_payment_tracking_number__icontains=bank_reference_upper) |
                Q(user__product_payments__bank_reference__icontains=bank_reference_upper) |
                Q(user__product_payments__payment_reference_id__icontains=bank_reference_upper)
            )
        
        # Payment method filter (for both event and product payments)
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            payment_method_upper = payment_method.upper()
            query_params.append(
                Q(participant_event_payments__method__method__iexact=payment_method_upper) |
                Q(user__product_payments__method__method__iexact=payment_method_upper)
            )
        
        # Payment package filter (for event payments only)
        payment_package = request.query_params.get("payment_package")
        if payment_package:
            try:
                package_id = uuid.UUID(payment_package)
                query_params.append(Q(participant_event_payments__package__id=package_id))
            except (ValueError, TypeError):
                # If not a valid UUID, try to filter by package name
                query_params.append(Q(participant_event_payments__package__name__icontains=payment_package))
            
        # Has merchandise filter
        has_merch = request.query_params.get("has_merch")
        if has_merch:
            if has_merch.lower() == 'true':
                # Participants with merchandise orders
                query_params.append(Q(user__carts__event=event))
            elif has_merch.lower() == 'false':
                # Participants without merchandise orders
                query_params.append(~Q(user__carts__event=event))
                
        # Registration date filter
        registration_date = request.query_params.get("registration_date")
        if registration_date:
            try:
                from datetime import datetime
                filter_date = datetime.fromisoformat(registration_date.replace('Z', '+00:00'))
                query_params.append(Q(registration_date__date=filter_date.date()))
            except ValueError:
                print(f"⚠️ Invalid registration_date format: {registration_date}")
                pass
            
        # Status filter
        status = request.query_params.get("status")
        if status:
            status_upper = status.upper()
            # Handle status filtering - check if it's a direct field or needs special handling
            if status_upper in ['REGISTERED', 'CONFIRMED', 'CANCELLED']:
                query_params.append(Q(status__iexact=status_upper))
            elif status_upper == 'CHECKED_IN':
                # Special case for checked in participants based on attendance
                from apps.events.models import EventDayAttendance
                from datetime import date
                today = date.today()
                query_params.append(
                    Q(user__event_attendance__day_date=today) &
                    Q(user__event_attendance__check_in_time__isnull=False) &
                    Q(user__event_attendance__check_out_time__isnull=True)
                )
            elif status_upper == 'NOT_CHECKED_IN':
                # Participants without check-in today
                from apps.events.models import EventDayAttendance
                from datetime import date
                today = date.today()
                query_params.append(
                    ~Q(user__event_attendance__day_date=today, 
                       user__event_attendance__check_in_time__isnull=False)
                )
            
        # Outstanding payments filter
        outstanding_payments = request.query_params.get("outstanding_payments")
        if outstanding_payments:
            if outstanding_payments.lower() == 'true':
                # Participants with outstanding payments/orders
                query_params.append(
                    Q(participant_event_payments__event=event, participant_event_payments__verified=False) |
                    Q(participant_event_payments__event=event, participant_event_payments__status=EventPayment.PaymentStatus.FAILED) |
                    Q(user__carts__event=event, user__carts__submitted=True, user__carts__approved=False, user__carts__active=True)
                )
            elif outstanding_payments.lower() == 'false':
                # Participants without outstanding payments/orders
                query_params.append(
                    ~Q(participant_event_payments__event=event, participant_event_payments__verified=False) &
                    ~Q(participant_event_payments__event=event, participant_event_payments__status=EventPayment.PaymentStatus.FAILED) &
                    ~Q(user__carts__event=event, user__carts__submitted=True, user__carts__approved=False, user__carts__active=True)
                )
        
        # Extra questions filtering
        # Format: ?extra_questions=<question_id>:<choice_id_or_text>,<question_id>:<choice_id_or_text>
        extra_questions_param = request.query_params.get("extra_questions")
        if extra_questions_param:
            question_filters = extra_questions_param.split(",")
            for question_filter in question_filters:
                try:
                    question_id, answer_value = question_filter.split(":", 1)
                    question_id = question_id.strip()
                    answer_value = answer_value.strip()
                    
                    # Try to parse as UUID (for choice-based answers)
                    if test_safe_uuid(answer_value):
                        # Filter by selected choice
                        query_params.append(
                            Q(event_question_answers__question__id=uuid.UUID(question_id)) &
                            Q(event_question_answers__selected_choices__id=uuid.UUID(answer_value))
                        )
                    else:
                        # Filter by text answer
                        query_params.append(
                            Q(event_question_answers__question__id=uuid.UUID(question_id)) &
                            Q(event_question_answers__answer_text__icontains=answer_value)
                        )
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Error parsing extra question filter '{question_filter}': {e}")
                    continue
            
        # Legacy questions_match parameter (keep for backwards compatibility)
        questions = request.query_params.get("questions_match")
        if questions:
            question_split = questions.split(",")
            for key_pair in question_split:
                try:
                    question_id, answer = key_pair.split("=")
                    answer = answer.strip()
                    
                    if test_safe_uuid(answer):
                        query_params.append(
                                Q(event_question_answers__question=uuid.UUID(question_id), event_question_answers__selected_choices=answer)
                            )
                    else:
                        query_params.append(
                            Q(event_question_answers__question=uuid.UUID(question_id), event_question_answers__answer_text=answer)
                            )
                except TypeError:
                    raise serializers.ValidationError("could not parse query correctly")
        try:
            # Base queryset with optimized joins
            participants = event.participants.select_related(
                'user', 'user__area_from', 'user__area_from__unit__chapter', 
                'user__area_from__unit__chapter__cluster'
            ).prefetch_related(
                'participant_event_payments', 'user__product_payments', 
                'user__carts', 'event_question_answers'
            )
            
            print(f"🔍 DEBUG participants - Base queryset count: {participants.count()}")
            
            # Apply filters
            if query_params:
                print(f"🔍 DEBUG participants - Applying {len(query_params)} filter(s)")
                for i, q in enumerate(query_params):
                    print(f"   Filter {i+1}: {q}")
                
                participants = participants.filter(*query_params).distinct()
                print(f"🔍 DEBUG participants - Filtered queryset count: {participants.count()}")
                # print(f"🔍 DEBUG participants - SQL Query: {participants.query}")
            else:
                print(f"🔍 DEBUG participants - No filters applied")
            
            # Apply ordering
            if order_by == 'recent_updates':
                # Order by most recent activity (payments, registrations) - simplified to avoid cross-model issues
                from django.db.models import Max, DateTimeField
                from django.db.models.functions import Coalesce
                
                # Simplified approach - avoid cross-model annotations that might cause select_related issues
                participants = participants.annotate(
                    last_payment_date=Max('participant_event_payments__created_at'),
                    # Use registration_date as baseline for comparison
                    activity_score=Coalesce('last_payment_date', 'registration_date', output_field=DateTimeField())
                ).order_by(
                    # Order by most recent payments/registrations
                    '-activity_score',
                    # Finally by registration date as fallback
                    '-registration_date'
                )
            elif order_by == 'name':
                participants = participants.order_by('user__first_name', 'user__last_name')
            elif order_by == 'registration_date':
                participants = participants.order_by('-registration_date')
            else:
                # Default ordering
                participants = participants.order_by('-registration_date')
                
        except (ValueError, ValidationError) as e:
            print(f"❌ ERROR in participants filtering: {e}")
            raise serializers.ValidationError("Invalid query parameters: " + str(e))
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR in participants filtering: {e}")
            print(f"❌ Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError("Error processing participants: " + str(e))

        # Get available filter options for dropdowns (from all participants, not filtered ones)
        try:
            all_participants = event.participants.select_related(
                'user', 'user__area_from', 'user__area_from__unit__chapter', 
                'user__area_from__unit__chapter__cluster'
            ).distinct()
            
            # Extract unique areas, chapters, and clusters for filter dropdowns
            areas = set()
            chapters = set()
            clusters = set()
            
            print(f"🔍 Processing {all_participants.count()} participants for filter options")
            
            for participant in all_participants:
                try:
                    user = participant.user
                    if user and hasattr(user, 'area_from') and user.area_from:
                        area_from = user.area_from
                        
                        # Area name
                        if hasattr(area_from, 'area_name') and area_from.area_name:
                            areas.add(area_from.area_name)
                            
                        # Chapter name (via unit.chapter)
                        if hasattr(area_from, 'unit') and area_from.unit:
                            unit = area_from.unit
                            if hasattr(unit, 'chapter') and unit.chapter:
                                chapter = unit.chapter
                                if hasattr(chapter, 'chapter_name') and chapter.chapter_name:
                                    chapters.add(chapter.chapter_name)
                                    
                                # Cluster name (via chapter.cluster)
                                if hasattr(chapter, 'cluster') and chapter.cluster:
                                    cluster = chapter.cluster
                                    if hasattr(cluster, 'cluster_id') and cluster.cluster_id:
                                        clusters.add(cluster.cluster_id)
                except Exception as e:
                    print(f"⚠️ Error processing participant {participant.id}: {e}")
                    continue
            
            print(f"📊 Filter options found - Areas: {len(areas)}, Chapters: {len(chapters)}, Clusters: {len(clusters)}")
            
            filter_options = {
                'areas': sorted(list(areas)),
                'chapters': sorted(list(chapters)), 
                'clusters': sorted(list(clusters))
            }
            
        except Exception as e:
            print(f"❌ Error building filter options: {e}")
            filter_options = {
                'areas': [],
                'chapters': [], 
                'clusters': []
            }

        # Apply pagination
        page = self.paginate_queryset(participants)        
        if page is not None:
            if simple:
                serializer = ListEventParticipantSerializer(page, many=True)
            else:
                serializer = ParticipantManagementSerializer(page, many=True)
            
            # Get paginated response and add filter options
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data['filter_options'] = filter_options
            return paginated_response
        
        # Return all results if pagination is disabled
        if simple:
            serializer = ListEventParticipantSerializer(participants, many=True)
        else:
            serializer = ParticipantManagementSerializer(participants, many=True)
        
        return Response({
            'results': serializer.data,
            'filter_options': filter_options
        })
    
    @action(detail=True, methods=['get'], url_name="event-payments", url_path="event-payments")
    def event_payments(self, request, pk=None, id=None):
        '''
        Retrieve a list of event payments for a specific event with filtering support.
        
        Supports the same filtering as participants:
        - ?search= (search by name, email, tracking number, bank reference)
        - ?bank_reference= (filter by bank reference or tracking number)
        - ?payment_method= (filter by payment method: STRIPE, BANK, CASH, etc.)
        - ?payment_package= (filter by package ID or name)
        - ?status= (filter by payment status: PENDING, SUCCEEDED, FAILED)
        - ?verified=true/false (filter by verification status)
        - ?area= (filter by participant's area)
        - ?chapter= (filter by participant's chapter)
        - ?cluster= (filter by participant's cluster)
        '''
        from apps.events.api.serializers import EventPaymentListSerializer
        
        event_lookup = id if id is not None else pk
        event = self.get_queryset().get(id=event_lookup)
        
        # Build query filters
        query_params = []
        
        # Always filter by event
        query_params.append(Q(event=event))
        
        # Search across multiple fields
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__user__first_name__icontains=search) |
                Q(user__user__last_name__icontains=search) |
                Q(user__user__primary_email__icontains=search) |
                Q(event_payment_tracking_number__icontains=search_upper) |
                Q(bank_reference__icontains=search_upper)
            )
        
        # Bank reference filter
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(bank_reference__icontains=bank_reference_upper) |
                Q(event_payment_tracking_number__icontains=bank_reference_upper)
            )
        
        # Payment method filter
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            query_params.append(Q(method__method__iexact=payment_method.upper()))
        
        # Payment package filter
        payment_package = request.query_params.get("payment_package")
        if payment_package:
            try:
                package_id = uuid.UUID(payment_package)
                query_params.append(Q(package__id=package_id))
            except (ValueError, TypeError):
                query_params.append(Q(package__name__icontains=payment_package))
        
        # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            query_params.append(Q(status__iexact=status_param.upper()))
        
        # Verified filter
        verified = request.query_params.get("verified")
        if verified:
            query_params.append(Q(verified=(verified.lower() == 'true')))
        
        # Area filtering
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__user__area_from__area_name__icontains=area) |
                        Q(user__user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
        
        # Chapter filtering
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    chapter_queries.append(Q(user__user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
        
        # Cluster filtering
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    cluster_queries.append(Q(user__user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
        
        # Build queryset
        payments = EventPayment.objects.select_related(
            'user', 'user__user', 'user__user__area_from',
            'user__user__area_from__unit__chapter',
            'user__user__area_from__unit__chapter__cluster',
            'method', 'package', 'event'
        ).filter(*query_params).distinct().order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(payments)
        if page is not None:
            serializer = EventPaymentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventPaymentListSerializer(payments, many=True)
        return Response({'results': serializer.data})
    
    @action(detail=True, methods=['get'], url_name="product-payments", url_path="product-payments")
    def product_payments(self, request, pk=None, id=None):
        '''
        Retrieve a list of product payments (cart payments) for a specific event with filtering support.
        
        Supports the same filtering as participants:
        - ?search= (search by name, email, payment reference, bank reference)
        - ?bank_reference= (filter by bank reference or payment reference)
        - ?payment_method= (filter by payment method: STRIPE, BANK, CASH, etc.)
        - ?status= (filter by payment status: PENDING, SUCCEEDED, FAILED)
        - ?approved=true/false (filter by approval status)
        - ?area= (filter by user's area)
        - ?chapter= (filter by user's chapter)
        - ?cluster= (filter by user's cluster)
        '''
        from apps.shop.api.serializers import ProductPaymentListSerializer
        
        event_lookup = id if id is not None else pk
        event = self.get_queryset().get(id=event_lookup)
        
        # Build query filters
        query_params = []
        
        # Always filter by event (through cart)
        query_params.append(Q(cart__event=event))
        
        # Search across multiple fields
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__primary_email__icontains=search) |
                Q(payment_reference_id__icontains=search_upper) |
                Q(bank_reference__icontains=search_upper) |
                Q(cart__order_reference_id__icontains=search_upper)
            )
        
        # Bank reference filter
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(bank_reference__icontains=bank_reference_upper) |
                Q(payment_reference_id__icontains=bank_reference_upper)
            )
        
        # Payment method filter
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            query_params.append(Q(method__method__iexact=payment_method.upper()))
        
        # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            query_params.append(Q(status__iexact=status_param.upper()))
        
        # Approved filter
        approved = request.query_params.get("approved")
        if approved:
            query_params.append(Q(approved=(approved.lower() == 'true')))
        
        # Area filtering
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__area_from__area_name__icontains=area) |
                        Q(user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
        
        # Chapter filtering
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    chapter_queries.append(Q(user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
        
        # Cluster filtering
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    cluster_queries.append(Q(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
        
        # Build queryset
        payments = ProductPayment.objects.select_related(
            'user', 'user__area_from',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster',
            'method', 'package', 'cart', 'cart__event'
        ).prefetch_related(
            'cart__orders'
        ).filter(*query_params).distinct().order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(payments)
        if page is not None:
            serializer = ProductPaymentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ProductPaymentListSerializer(payments, many=True)
        return Response({'results': serializer.data})
    
    @action(detail=True, methods=['post'], url_name="register", url_path="register")
    def register(self, request, id=None):
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
        
        # Broadcast WebSocket update for new participant registration
        try:
            participant_data = serialize_participant_for_websocket(participant)
            websocket_notifier.notify_participant_registered(
                event_id=str(event.id),
                participant_data=participant_data
            )
            
            # Notify dashboard users about participant count change
            supervisor_ids = get_event_supervisors(event)
            websocket_notifier.notify_event_update(
                user_ids=supervisor_ids,
                event_id=str(event.id),
                update_type='participant_registered',
                data={'participant_id': str(participant.id)}
            )
        except Exception as e:
            # Log the error but don't fail the registration process
            print(f"WebSocket notification error during registration: {e}")
        
        serializer = SimplifiedEventParticipantSerializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name="remove-participant", url_path="remove-participant")
    def remove_participant(self, request, id=None):
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
    def attendance(self, request, id=None):
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
    def service_team(self, request, id=None):
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
    def add_service_member(self, request, id=None):
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
    def remove_service_member(self, request, id=None):
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
    def talks(self, request, id=None):
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
    def workshops(self, request, id=None):
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
    def products(self, request, id=None):
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

    @action(detail=True, methods=['get'], url_name="payment-methods", url_path="payment-methods")
    def product_payment_methods(self, request, pk=None):
        '''
        Retrieve a list of product payment methods for a specific event.
        '''
        event = self.get_object()
        payment_methods = event.product_payment_methods.all()
        page = self.paginate_queryset(payment_methods)
        if page is not None:
            serializer = EventPaymentMethodSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = EventPaymentMethodSerializer(payment_methods, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], url_name="product-payment-methods", url_path="product-payment-methods")
    def product_payment_methods(self, request, id=None):
        '''
        Retrieve and create merchandise payment methods for a specific event.
        '''
        if request.method == 'GET':
            event = self.get_object()
            payment_methods = event.product_payment_methods.filter(is_active=True)
            page = self.paginate_queryset(payment_methods)
            if page is not None:
                serializer = ProductPaymentMethodSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = ProductPaymentMethodSerializer(payment_methods, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            event = self.get_object()
            self.check_object_permissions(request, event) 
            self.check_permissions(request) 
            serializer = ProductPaymentMethodSerializer(data=request.data, context={'event': event})
            if serializer.is_valid():
                serializer.save(event=event)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['put', 'patch', 'delete'], url_name="product-payment-method-detail", url_path="product-payment-methods/(?P<method_id>[^/.]+)")
    def product_payment_method_detail(self, request, id=None, method_id=None):
        '''
        Update or delete a specific merchandise payment method for an event.
        '''
        event = self.get_object()
        self.check_object_permissions(request, event)
        self.check_permissions(request)
        
        try:
            payment_method = event.product_payment_methods.get(id=method_id)
        except event.product_payment_methods.model.DoesNotExist:
            return Response(
                {'error': _('Payment method not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method in ['PUT', 'PATCH']:
            serializer = ProductPaymentMethodSerializer(
                payment_method, 
                data=request.data, 
                partial=request.method == 'PATCH',
                context={'event': event}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            payment_method.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=["GET"], url_name="check-in-users", url_path="check-in-users")
    def get_check_in_users(self, request, id=None):
        '''
        To filter by cluster use ?area=cluster_d
        '''
        query_params = []
        
        area = request.query_params.get("area")
        if area:
            if area.startswith("cluster_"):
                cluster_id = area[-1].upper()
                print(cluster_id)
                query_params.append(Q(user__area_from__unit__chapter__cluster__cluster_id=cluster_id))
            else:
                query_params.append(
                    (Q(user__area_from__area_name=area) | Q(user__area_from__area_code=area) | 
                    Q(user__area_from__unit__chapter__chapter_name=area.capitalize())) 
                )
        participants = EventParticipant.objects.filter(
            (Q(user__event_attendance__stale=True) | Q(user__event_attendance=None)),
            event=id,
            *query_params,
        ).distinct()
        
        return Response([
            {
                "full_name": f"{p.user.first_name} {p.user.last_name}",
                "picture": p.user.profile_picture.url if p.user.profile_picture else None,
                "area": p.user.area_from.area_name if p.user.area_from else None,
                "chapter": p.user.area_from.unit.chapter.chapter_name if p.user.area_from and p.user.area_from.unit and p.user.area_from.unit.chapter else None,
                "cluster": p.user.area_from.unit.chapter.cluster.cluster_id if p.user.area_from and p.user.area_from.unit and p.user.area_from.unit.chapter and p.user.area_from.unit.chapter.cluster else None
            } for p in participants.all()
        ])
        
    @action(detail=True, methods=["GET"], url_name="filter-options", url_path="filter-options")
    def filter_options(self, request, id=None):
        """
        Get available filter options for participant filtering.
        Returns areas, chapters, clusters, and extra questions with their choices.
        """
        try:
            from apps.events.models.location_models import AreaLocation, ChapterLocation, ClusterLocation
            from apps.events.models import ExtraQuestion
            
            # Get the current event
            event = self.get_object()
            
            # Get areas, chapters, and clusters that have participants in this event
            participants_queryset = event.participants.all()
            
            # Extract unique location values from participants
            areas_with_participants = set()
            chapters_with_participants = set()
            clusters_with_participants = set()
            
            for participant in participants_queryset:
                if participant.user and participant.user.area_from:
                    area_obj = participant.user.area_from
                    if area_obj.area_name:
                        areas_with_participants.add(area_obj.area_name)
                    if area_obj.unit and area_obj.unit.chapter and area_obj.unit.chapter.chapter_name:
                        chapters_with_participants.add(area_obj.unit.chapter.chapter_name)
                    if area_obj.unit and area_obj.unit.chapter and area_obj.unit.chapter.cluster and area_obj.unit.chapter.cluster.cluster_id:
                        clusters_with_participants.add(area_obj.unit.chapter.cluster.cluster_id)
            
            # Convert to sorted lists
            areas = sorted(list(areas_with_participants))
            chapters = sorted(list(chapters_with_participants))
            clusters = sorted(list(clusters_with_participants))
            
            # Get extra questions for this event
            extra_questions = ExtraQuestion.objects.filter(event=event).prefetch_related('choices').order_by('order')
            
            extra_questions_data = []
            for question in extra_questions:
                question_data = {
                    'id': str(question.id),
                    'question_name': question.question_name,
                    'question_body': question.question_body,
                    'question_type': question.question_type,
                    'question_type_display': question.get_question_type_display(),
                    'required': question.required,
                    'order': question.order,
                    'choices': []
                }
                
                # Add choices for CHOICE and MULTICHOICE questions
                if question.question_type in ['CHOICE', 'MULTICHOICE']:
                    choices = question.choices.all().order_by('order')
                    question_data['choices'] = [
                        {
                            'id': str(choice.id),
                            'text': choice.text,
                            'value': choice.value or choice.text,
                            'order': choice.order
                        }
                        for choice in choices
                    ]
                
                extra_questions_data.append(question_data)
            
            return Response({
                'areas': areas,
                'chapters': chapters,
                'clusters': clusters,
                'extra_questions': extra_questions_data
            })
        except Exception as e:
            print(f"❌ Error getting filter options: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'areas': [],
                'chapters': [],
                'clusters': [],
                'extra_questions': []
            })

        

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
    
    def get_serializer_class(self):
        """
        Use optimized serializer for list views to reduce response size by 70-80%
        Use full serializer for create/update operations that need complete data
        """
        if self.action == 'list':
            return ParticipantManagementSerializer
        elif self.action in ['retrieve'] and self.request.query_params.get('summary', 'false').lower() == 'true':
            return ParticipantManagementSerializer
        return EventParticipantSerializer
        
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
    
    #TODO: add role to a service team member AND NOT a participant - low priority
    #TODO: cancel booking        
    
    @action(detail=True, methods=['post'], url_name="check-in", url_path="check-in")
    def check_in(self, request, event_pax_id=None):
        '''
        Check in a participant to the event. Returns {participant: date, is_checked_in: bool}
        '''
        # TODO: ensure only service team are allowed to check in
        data = request.data
        
        try:
            event_uuid = data.get("event_uuid")
            event_uuid = uuid.UUID(event_uuid)
        except (ValueError, TypeError):
            raise serializers.ValidationError({"error": "invalid or missing event UUID"})
        
        participant = get_object_or_404(
            EventParticipant,
            Q(event_pax_id = event_pax_id) | Q(secondary_reference_id = event_pax_id),
            event=event_uuid
        )
        
        event: Event = participant.event   
        check_in_datetime_utc = timezone.now()
        
        # Convert to London time for storage
        import pytz
        london_tz = pytz.timezone('Europe/London')
        check_in_datetime = check_in_datetime_utc.astimezone(london_tz)

        if check_in_datetime_utc < event.start_date:
            raise serializers.ValidationError("cannot check in participant as the event has not yet started")
        
        if participant.status != EventParticipant.ParticipantStatus.ATTENDED:
            participant.status = EventParticipant.ParticipantStatus.ATTENDED
            participant.attended_date = timezone.now()
            participant.save()
        
        is_checked_in = EventDayAttendance.objects.filter(
            event=participant.event, 
            user=participant.user,
            day_date = check_in_datetime.date(),
            check_out_time=None,
        ).exists()
        if not is_checked_in:
            EventDayAttendance.objects.create(
                event = participant.event,
                user = participant.user,
                check_in_time = check_in_datetime.time(),  # Now stores London time
                day_date = check_in_datetime.date(),
                day_id = data.get("day_id", 1)
            )
            
            # Broadcast WebSocket update for check-in
            try:
                print(f"🔔 CHECK-IN API - Starting WebSocket notification for participant: {participant.user.first_name} {participant.user.last_name}")
                print(f"🔔 CHECK-IN API - Event: {participant.event.name} (ID: {participant.event.id})")
                
                participant_data = serialize_participant_for_websocket(participant)
                print(f"📊 CHECK-IN API - Serialized participant data for: {participant_data.get('user', {}).get('first_name', 'Unknown')}")
                print(f"📊 CHECK-IN API - Checked in status: {participant_data.get('checked_in', False)}")
                
                websocket_notifier.notify_checkin_update(
                    event_id=str(participant.event.id),
                    participant_data=participant_data,
                    action='checkin'
                )
                
                # Notify dashboard users about participant count change
                supervisor_ids = get_event_supervisors(participant.event)
                websocket_notifier.notify_event_update(
                    user_ids=supervisor_ids,
                    event_id=str(participant.event.id),
                    update_type='participant_checked_in',
                    data={'participant_id': str(participant.id)}
                )
                print(f"✅ CHECK-IN API - WebSocket notification sent successfully!")
                
            except Exception as e:
                # Log the error but don't fail the check-in process
                print(f"❌ CHECK-IN API - WebSocket notification error: {e}")
                import traceback
                print(f"❌ CHECK-IN API - Full traceback: {traceback.format_exc()}")
            
        serializer = ParticipantManagementSerializer(participant)
        return Response({
            "participant": serializer.data,
            "already_checked_in": is_checked_in
        })
    
    @action(detail=True, methods=['post'], url_name="check-out", url_path="check-out")
    def check_out(self, request, event_pax_id=None):
        '''
        Check out a participant from the event.
        '''
        # TODO: ensure only service team are allowed to check in
        data = request.data
        try:
            event_uuid = data.get("event_uuid")
            event_uuid = uuid.UUID(event_uuid)
        except (ValueError, TypeError):
            raise serializers.ValidationError({"error": "invalid or missing event UUID"})

        participant = get_object_or_404(
            EventParticipant,
            Q(event_pax_id = event_pax_id) | Q(secondary_reference_id = event_pax_id),
            event=event_uuid
        )
        check_out_datetime_utc = timezone.now()
        
        # Convert to London time for storage
        import pytz
        london_tz = pytz.timezone('Europe/London')
        check_out_datetime = check_out_datetime_utc.astimezone(london_tz)
                
        checked_in = EventDayAttendance.objects.filter(
            event=participant.event, 
            user=participant.user,
            day_date = check_out_datetime.date(),
            check_out_time=None
        )
        if checked_in.exists():
            first = checked_in.first()
            first.check_out_time = check_out_datetime.time()  # Now stores London time
            first.save()
            
            # Broadcast WebSocket update for check-out
            try:
                print(f"🔔 CHECK-OUT API - Starting WebSocket notification for participant: {participant.user.first_name} {participant.user.last_name}")
                print(f"🔔 CHECK-OUT API - Event: {participant.event.name} (ID: {participant.event.id})")
                
                participant_data = serialize_participant_for_websocket(participant)
                print(f"📊 CHECK-OUT API - Serialized participant data for: {participant_data.get('user', {}).get('first_name', 'Unknown')}")
                print(f"📊 CHECK-OUT API - Checked in status: {participant_data.get('checked_in', False)}")
                
                websocket_notifier.notify_checkin_update(
                    event_id=str(participant.event.id),
                    participant_data=participant_data,
                    action='checkout'
                )
                
                # Notify dashboard users about participant count change
                supervisor_ids = get_event_supervisors(participant.event)
                websocket_notifier.notify_event_update(
                    user_ids=supervisor_ids,
                    event_id=str(participant.event.id),
                    update_type='participant_checked_out',
                    data={'participant_id': str(participant.id)}
                )
                print(f"✅ CHECK-OUT API - WebSocket notification sent successfully!")
                
            except Exception as e:
                # Log the error but don't fail the check-out process
                print(f"❌ CHECK-OUT API - WebSocket notification error: {e}")
                import traceback
                print(f"❌ CHECK-OUT API - Full traceback: {traceback.format_exc()}")
        else:
            raise serializers.ValidationError("cannot checkout this user as they are not checked in")
        
        serializer = ParticipantManagementSerializer(participant)
        return Response(serializer.data)
        
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        data = response.data
        
        # Send booking confirmation email with QR code
        try:
            # Get the created participant
            event_user_id = data.get("event_user_id")
            if event_user_id:
                participant = EventParticipant.objects.get(event_pax_id=event_user_id)
                # Send email asynchronously (non-blocking)
                from threading import Thread
                email_thread = Thread(target=send_booking_confirmation_email, args=(participant,))
                email_thread.start()
                print(f"📧 Booking confirmation email queued for {event_user_id}")
        except Exception as e:
            # Don't fail the registration if email fails
            print(f"⚠️ Failed to queue booking confirmation email: {e}")
        
        return Response(
            {   
             "event_user_id": data["event_user_id"], 
             "is_paid": all(p['status'] == 'SUCCEEDED' for p in data['event_payments']), 
             "payment_method": data['event_payments'][0]['method'] if data['event_payments'] else 'No payment method', 
             "needs_verification": any(not p['verified'] for p in data['event_payments'])
            }, status=response.status_code)
        
    @action(detail=True, methods=['post'], url_name="confirm-payment", url_path="confirm-payment")
    def confirm_registration_payment(self, request, event_pax_id=None):
        '''
        Confirm a participant's registration for an event. This must be done if they have paid
        Only event organizers/admins can confirm registrations.
        '''
        # TODO: ensure only organisers can do this
        participant = self.get_object()
        if participant.status != EventParticipant.ParticipantStatus.REGISTERED:
            return Response(
                {'error': _('Only participants with REGISTERED status can be confirmed.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment = get_object_or_404(EventPayment, user=participant)
        
        # Check if already verified
        already_verified = payment.verified
        
        payment.verified = True
        payment.paid_at = timezone.now()
        payment.status = EventPayment.PaymentStatus.SUCCEEDED
        payment.save()
        
        # Send confirmation email in background if newly verified
        if not already_verified:
            def send_email():
                try:
                    send_payment_verification_email(participant)
                    print(f"📧 Registration payment verification email queued for {participant.event_pax_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send payment verification email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()
        
        serializer = self.get_serializer(participant)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="confirm-merch-payment", url_path="confirm-merch-payment")
    def confirm_merch_order_payment(self, request, event_pax_id=None):
        '''
        Confirm a participant's merchandise order payment for an event.
        Only event organizers/admins can confirm payments.
        '''
        # TODO: ensure only organisers can do this
        data = request.data
        participant = get_object_or_404(EventParticipant, event_pax_id=event_pax_id)
        cart = data.get('cart_id')
        if not cart:
            return Response(
                {'error': _('Cart ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        cart_instance = get_object_or_404(EventCart, uuid=cart, user=participant.user)
        if not cart_instance.submitted:
            return Response(
                {'error': _('Cart must be submitted before confirming payment.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        product_payment = get_object_or_404(ProductPayment, cart=cart_instance, user=participant.user)
        
        # Check if already approved
        already_approved = product_payment.approved
        
        product_payment.status = ProductPayment.PaymentStatus.SUCCEEDED
        product_payment.approved = True
        product_payment.paid_at = timezone.now()
        product_payment.save()
        
        cart_instance.approved = True
        cart_instance.save()
        
        # Send confirmation email in background if newly approved
        if not already_approved:
            def send_email():
                try:
                    send_payment_verified_email(cart_instance, product_payment)
                    print(f"📧 Merch order payment verification email queued for order {cart_instance.order_reference_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send merch payment verification email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()

        serializer = self.get_serializer(participant)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="create-merch-cart", url_path="create-merch-cart")
    def create_merch_cart(self, request, event_pax_id=None):
        '''
        Create a new merchandise cart for a participant with manual orders.
        Only event organizers/admins can create carts for participants.
        
        Expected payload:
        {
            "user_id": "user-uuid",
            "event_id": "event-uuid", 
            "notes": "Optional cart notes",
            "shipping_address": "Optional shipping address",
            "orders": [
                {
                    "product_uuid": "product-uuid",
                    "product_name": "Product Name",
                    "quantity": 2,
                    "price_at_purchase": 15.00,
                    "size": "LG",
                    "size_id": 154
                }
            ]
        }
        '''
        
        try:
            data = request.data
            participant = self.get_object()
            
            # Validate required fields
            orders_data = data.get('orders', [])
            if not orders_data:
                return Response(
                    {'error': _('At least one order is required.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate each order has required fields
            for i, order_data in enumerate(orders_data):
                required_fields = ['product_uuid', 'quantity', 'price_at_purchase']
                missing_fields = [field for field in required_fields if field not in order_data]
                if missing_fields:
                    return Response(
                        {'error': f'Order {i+1} missing required fields: {", ".join(missing_fields)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create the cart
            cart = EventCart.objects.create(
                user=participant.user,
                event=participant.event,
                notes=data.get('notes', ''),
                shipping_address=data.get('shipping_address', ''),
                total=0,  # Will be calculated below
                active=True,
                submitted=False,
                approved=False
            )
            
            total_amount = 0
            
            # Create orders for each product
            for order_data in orders_data:
                try:
                    # Get the product
                    product = EventProduct.objects.get(
                        uuid=order_data['product_uuid'], 
                        event=participant.event
                    )
                    
                    # Get size if specified
                    size_instance = None
                    if order_data.get('size_id'):
                        size_instance = ProductSize.objects.get(
                            id=order_data['size_id'],
                            product=product
                        )
                    
                    # Validate quantity
                    quantity = int(order_data['quantity'])
                    if quantity <= 0:
                        raise ValueError("Quantity must be greater than 0")
                    
                    if quantity > product.maximum_order_quantity:
                        raise ValueError(f"Quantity exceeds maximum order quantity of {product.maximum_order_quantity}")
                    
                    # Calculate price
                    price_at_purchase = float(order_data['price_at_purchase'])
                    if price_at_purchase < 0:
                        raise ValueError("Price cannot be negative")
                    
                    # Create the order
                    order = EventProductOrder.objects.create(
                        product=product,
                        cart=cart,
                        quantity=quantity,
                        price_at_purchase=price_at_purchase,
                        size=size_instance,
                        uses_size=size_instance is not None,
                        status=EventProductOrder.Status.PENDING
                    )
                    
                    # Add to total
                    total_amount += price_at_purchase * quantity
                    
                except EventProduct.DoesNotExist:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Product with UUID {order_data.get("product_uuid")} not found.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except ProductSize.DoesNotExist:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Size with ID {order_data.get("size_id")} not found for this product.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except (ValueError, KeyError) as e:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Invalid order data: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Update cart total
            cart.total = total_amount
            cart.save()
            
            # Return cart data
            serializer = EventCartMinimalSerializer(cart)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create cart: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['patch'], url_name="update-merch-order", url_path="update-merch-order/(?P<order_id>[^/.]+)")
    def update_merch_order(self, request, event_pax_id=None, order_id=None):
        '''
        Update an individual merchandise order for a participant.
        Only event organizers/admins can update orders.
        
        Expected payload:
        {
            "product_name": "Updated Product Name",
            "size": "MD",
            "quantity": 3,
            "price_at_purchase": 20.00
        }
        '''
        
        try:
            participant = self.get_object()
            
            # Get the order
            try:
                order = EventProductOrder.objects.get(
                    id=order_id,
                    cart__user=participant.user,
                    cart__event=participant.event
                )
            except EventProductOrder.DoesNotExist:
                return Response(
                    {'error': _('Order not found.')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if cart is already approved (can't modify approved carts)
            if order.cart.approved:
                return Response(
                    {'error': _('Cannot modify orders in approved carts.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            data = request.data
            updated_fields = {}  # Track what changed for email notification
            
            # Update fields if provided
            if 'quantity' in data:
                quantity = int(data['quantity'])
                if quantity <= 0:
                    return Response(
                        {'error': _('Quantity must be greater than 0.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if quantity > order.product.maximum_order_quantity:
                    return Response(
                        {'error': f'Quantity exceeds maximum order quantity of {order.product.maximum_order_quantity}.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if order.quantity != quantity:
                    updated_fields['quantity'] = quantity
                    order.quantity = quantity
            
            if 'price_at_purchase' in data:
                price = float(data['price_at_purchase'])
                if price < 0:
                    return Response(
                        {'error': _('Price cannot be negative.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if order.price_at_purchase != price:
                    updated_fields['price_at_purchase'] = price
                    order.price_at_purchase = price
            
            # Handle size updates
            if 'size' in data:
                size_value = data['size']
                if size_value:
                    try:
                        size_instance = ProductSize.objects.get(
                            size=size_value,
                            product=order.product
                        )
                        if order.size != size_instance:
                            updated_fields['size'] = size_value
                            order.size = size_instance
                            order.uses_size = True
                    except ProductSize.DoesNotExist:
                        return Response(
                            {'error': f'Size "{size_value}" not available for this product.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    if order.size is not None:
                        updated_fields['size'] = 'None (removed)'
                    order.size = None
                    order.uses_size = False
            
            order.save()
            
            # Recalculate cart total
            cart = order.cart
            cart.total = sum(
                (o.price_at_purchase or 0) * o.quantity 
                for o in cart.orders.all()
            )
            cart.save()
            
            # Send email notification if any changes were made
            if updated_fields:
                def send_email():
                    try:
                        send_order_update_email(cart, order, updated_fields)
                        print(f"📧 Order update email queued for order {order.id} in cart {cart.order_reference_id}")
                    except Exception as e:
                        print(f"⚠️ Failed to send order update email: {e}")
                
                email_thread = threading.Thread(target=send_email)
                email_thread.start()
            
            return Response(
                {'message': _('Order updated successfully.')},
                status=status.HTTP_200_OK
            )
            
        except (ValueError, KeyError) as e:
            return Response(
                {'error': f'Invalid data: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to update order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['patch'], url_name="cancel-merch-order", url_path="cancel-merch-order/(?P<order_id>[^/.]+)")
    def cancel_merch_order(self, request, event_pax_id=None, order_id=None):
        '''
        Cancel an individual merchandise order for a participant.
        Only event organizers/admins can cancel orders.
        '''
        
        try:
            participant = self.get_object()
            
            # Get the order
            try:
                order = EventProductOrder.objects.get(
                    id=order_id,
                    cart__user=participant.user,
                    cart__event=participant.event
                )
            except EventProductOrder.DoesNotExist:
                return Response(
                    {'error': _('Order not found.')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if cart is already approved (can't cancel from approved carts)
            if order.cart.approved:
                return Response(
                    {'error': _('Cannot cancel orders in approved carts.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update status to cancelled
            order.status = EventProductOrder.Status.CANCELLED
            order.save()
            
            # Recalculate cart total (excluding cancelled orders)
            cart = order.cart
            cart.total = sum(
                (o.price_at_purchase or 0) * o.quantity 
                for o in cart.orders.filter(status__in=[
                    EventProductOrder.Status.PENDING,
                    EventProductOrder.Status.PURCHASED
                ])
            )
            cart.save()
            
            return Response(
                {'message': _('Order cancelled successfully.')},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {'error': f'Failed to cancel order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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