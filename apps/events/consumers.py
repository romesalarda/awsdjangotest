import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.events.models import Event, EventParticipant, EventDayAttendance
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import pytz

User = get_user_model()


def safe_json_dumps(data):
    """Helper function to safely serialize data including Decimal objects"""
    return json.dumps(data, cls=DjangoJSONEncoder)


def convert_to_london_time(dt):
    """Handle timezone conversion for different field types"""
    if not dt:
        return None
    
    # Handle TimeField (time object) vs DateTimeField (datetime object)
    if hasattr(dt, 'date'):
        # It's a datetime object (DateTimeField) - convert to London time
        if not timezone.is_aware(dt):
            # If it's naive, assume it's UTC
            dt = timezone.make_aware(dt, pytz.UTC)
        
        london_tz = pytz.timezone('Europe/London')
        return dt.astimezone(london_tz)
    else:
        # It's a time object (TimeField) - already stored in London time, return as-is
        return dt


class EventCheckInConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live event check-in updates.
    Allows real-time monitoring of participant check-ins for specific events.
    """

    async def connect(self):
        # Get event ID from URL route
        self.event_id = self.scope['url_route']['kwargs']['event_id']
        self.event_group_name = f'event_checkin_{self.event_id}'
        
        print(f"🔌 WebSocket Connect - Event ID: {self.event_id}, Group: {self.event_group_name}")

        # Check if user is authenticated
        user = self.scope["user"]
        if user.is_anonymous:
            print(f"❌ WebSocket Connect FAILED - User is anonymous")
            await self.close()
            return

        print(f"👤 WebSocket Connect - User: {user.username} (ID: {user.id})")

        # Check if user has permission to monitor this event
        has_permission = await self.check_event_permission(user, self.event_id)
        if not has_permission:
            print(f"❌ WebSocket Connect FAILED - User {user.username} has no permission for event {self.event_id}")
            await self.close()
            return

        print(f"✅ WebSocket Connect - User {user.username} has permission for event {self.event_id}")

        # Join event group
        await self.channel_layer.group_add(
            self.event_group_name,
            self.channel_name
        )

        print(f"📡 WebSocket Connect - Added to group {self.event_group_name}")

        await self.accept()

        # Send initial event data
        await self.send_initial_data()

    async def disconnect(self, close_code):
        # Leave event group
        await self.channel_layer.group_discard(
            self.event_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """
        Handle messages from WebSocket client
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            if message_type == 'get_participants':
                # Handle filter parameters from client
                filters = text_data_json.get('filters', {})
                order_by = text_data_json.get('order_by', 'recent_updates')
                page = text_data_json.get('page', 1)
                page_size = text_data_json.get('page_size', 50)
                print(f"🔍 WebSocket get_participants - Filters: {filters}")
                await self.send_participants_data(filters, order_by, page, page_size)
            elif message_type == 'update_filters':
                # Handle filter updates
                filters = text_data_json.get('filters', {})
                order_by = text_data_json.get('order_by', 'recent_updates')
                page = text_data_json.get('page', 1)
                page_size = text_data_json.get('page_size', 50)
                await self.send_participants_data(filters, order_by, page, page_size)
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': text_data_json.get('timestamp')
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))

    async def checkin_update(self, event):
        """
        Handle check-in update messages from the group
        """
        participant_name = event['participant'].get('user', {}).get('first_name', 'Unknown')
        print(f"📤 WebSocket SENDING checkin_update - Group: {self.event_group_name}, Participant: {participant_name}, Action: {event['action']}")
        
        await self.send(text_data=safe_json_dumps({
            'type': 'checkin_update',
            'participant': event['participant'],
            'action': event['action'],  # 'checkin' or 'checkout'
            'timestamp': event['timestamp']
        }))
        
        print(f"✅ WebSocket SENT checkin_update to client")

    async def participant_registered(self, event):
        """
        Handle new participant registration
        """
        participant_name = event['participant'].get('user', {}).get('first_name', 'Unknown')
        print(f"📤 WebSocket SENDING participant_registered - Group: {self.event_group_name}, Participant: {participant_name}")
        
        await self.send(text_data=safe_json_dumps({
            'type': 'participant_registered',
            'participant': event['participant'],
            'timestamp': event['timestamp']
        }))

    async def send_initial_data(self):
        """
        Send initial event and participant data when client connects
        """
        event_data = await self.get_event_data()
        participants_data = await self.get_participants_data()
        
        await self.send(text_data=safe_json_dumps({
            'type': 'initial_data',
            'event': event_data,
            'participants': participants_data['results'],
            'pagination': {
                'count': participants_data['count'],
                'page': 1,
                'page_size': 50,
                'total_pages': participants_data['total_pages'],
                'has_next': participants_data['has_next'],
                'has_previous': participants_data['has_previous']
            },
            'filter_options': participants_data['filter_options']
        }))

    async def send_participants_data(self, filters=None, order_by='recent_updates', page=1, page_size=50):
        """
        Send current participants data with filtering, ordering, and pagination
        """
        participants_data = await self.get_participants_data(filters, order_by, page, page_size)
        
        await self.send(text_data=safe_json_dumps({
            'type': 'participants_data',
            'participants': participants_data['results'],
            'pagination': {
                'count': participants_data['count'],
                'page': page,
                'page_size': page_size,
                'total_pages': participants_data['total_pages'],
                'has_next': participants_data['has_next'],
                'has_previous': participants_data['has_previous']
            },
            'filter_options': participants_data['filter_options']
        }))

    @database_sync_to_async
    def check_event_permission(self, user, event_id):
        """
        Check if user has permission to monitor this event
        """
        try:
            event = Event.objects.get(id=event_id)
            
            is_superuser = user.is_superuser
            is_creator = event.created_by == user
            is_service_team = event.service_team_members.filter(user=user).exists()
            
            has_permission = is_superuser or is_creator or is_service_team
            
            print(f"🔐 PERMISSION CHECK - User: {user.username} (ID: {user.id})")
            print(f"   - Event: {event.name} (ID: {event.id})")
            print(f"   - Is Superuser: {is_superuser}")
            print(f"   - Is Creator: {is_creator} (Creator: {event.created_by.username if event.created_by else 'None'})")
            print(f"   - Is Service Team: {is_service_team}")
            print(f"   - FINAL PERMISSION: {has_permission}")
            
            return has_permission
            
        except Event.DoesNotExist:
            print(f"❌ PERMISSION CHECK FAILED - Event {event_id} does not exist")
            return False

    @database_sync_to_async
    def get_event_data(self):
        """
        Get basic event information
        """
        try:
            event = Event.objects.get(id=self.event_id)
            return {
                'id': str(event.id),
                'name': event.name,
                'start_date': event.start_date.isoformat() if event.start_date else None,
                'end_date': event.end_date.isoformat() if event.end_date else None,
                'participant_count': EventParticipant.objects.filter(event=event).count()
            }
        except Event.DoesNotExist:
            return None

    @database_sync_to_async
    def get_participants_data(self, filters=None, order_by='recent_updates', page=1, page_size=50):
        """
        Get current participants data with check-in status, filtering, ordering, and pagination
        """
        from django.db.models import Q, Max
        from django.core.paginator import Paginator
        import math
        
        try:
            event = Event.objects.get(id=self.event_id)
            
            # Base queryset with optimized joins
            participants = EventParticipant.objects.filter(event=event).select_related(
                'user', 'user__area_from', 'user__area_from__unit__chapter', 
                'user__area_from__unit__chapter__cluster'
            ).prefetch_related(
                'participant_event_payments', 'user__product_payments', 
                'user__carts', 'event_question_answers'
            )
            
            # Apply filters if provided
            if filters:
                filter_conditions = Q()
                
                # Search filter
                if filters.get('search'):
                    search_term = filters['search']
                    filter_conditions &= (
                        Q(user__first_name__icontains=search_term) |
                        Q(user__last_name__icontains=search_term) |
                        Q(user__primary_email__icontains=search_term) |
                        Q(user__member_id__icontains=search_term) |
                        Q(event_pax_id__icontains=search_term)
                    )
                
                # Area filter
                if filters.get('area'):
                    area_term = filters['area']
                    filter_conditions &= (
                        Q(user__area_from__area_name__icontains=area_term) |
                        Q(user__area_from__area_code__icontains=area_term)
                    )
                
                # Chapter filter
                if filters.get('chapter'):
                    filter_conditions &= Q(user__area_from__unit__chapter__chapter_name__icontains=filters['chapter'])
                
                # Cluster filter  
                if filters.get('cluster'):
                    filter_conditions &= Q(user__area_from__unit__chapter__cluster__cluster_id__icontains=filters['cluster'])
                
                # Status filter
                if filters.get('status'):
                    status_upper = filters['status'].upper()
                    if status_upper in ['REGISTERED', 'CONFIRMED', 'CANCELLED']:
                        filter_conditions &= Q(status__iexact=status_upper)
                    elif status_upper == 'CHECKED_IN':
                        # Participants checked in today
                        from datetime import date
                        today = date.today()
                        filter_conditions &= (
                            Q(user__event_attendance__day_date=today) &
                            Q(user__event_attendance__check_in_time__isnull=False) &
                            Q(user__event_attendance__check_out_time__isnull=True)
                        )
                    elif status_upper == 'NOT_CHECKED_IN':
                        # Participants not checked in today
                        from datetime import date
                        today = date.today()
                        filter_conditions &= ~Q(
                            user__event_attendance__day_date=today,
                            user__event_attendance__check_in_time__isnull=False
                        )
                    elif status_upper == 'PENDING_PAYMENT':
                        filter_conditions &= Q(verified=False)
                
                # Identity filter (email/member ID)
                if filters.get('identity'):
                    identity_term = filters['identity']
                    filter_conditions &= (
                        Q(user__primary_email__icontains=identity_term) |
                        Q(user__member_id__icontains=identity_term) |
                        Q(user__first_name__icontains=identity_term) |
                        Q(user__last_name__icontains=identity_term) |
                        Q(event_pax_id__icontains=identity_term)
                    )
                
                # Bank reference filter#
                # TODO: also get bank reference from ProductPayment linked to user
                if filters.get('bank_reference'):
                    filter_conditions &= Q(participant_event_payments__bank_reference__icontains=filters['bank_reference'])
                    # TODO: also get bank reference from ProductPayment linked to user
                    filter_conditions |= Q(user__product_payments__bank_reference__icontains=filters['bank_reference'])
                
                # Outstanding payments filter
                if filters.get('outstanding_payments'):
                    if filters['outstanding_payments'].lower() == 'true':
                        filter_conditions &= Q(verified=False)  # Has outstanding payments
                    elif filters['outstanding_payments'].lower() == 'false':
                        filter_conditions &= Q(verified=True)   # No outstanding payments
                
                # Extra question filters
                if filters.get('question_filters'):
                    print(f"🔍 Processing question_filters: {filters['question_filters']}")
                    for question_filter in filters['question_filters']:
                        print(f"🔍 Processing single question_filter: {question_filter} (type: {type(question_filter)})")
                        question_id = question_filter.get('question_id')
                        question_value = question_filter.get('value')
                        question_type = question_filter.get('question_type')
                        
                        if not question_id or not question_value:
                            continue
                            
                        # Get the question to understand its type
                        from apps.events.models import ExtraQuestion, QuestionAnswer
                        try:
                            question = ExtraQuestion.objects.get(id=question_id)
                        except ExtraQuestion.DoesNotExist:
                            continue
                        
                        # Build filter conditions based on question type
                        if question.question_type in ['TEXT', 'TEXTAREA', 'INTEGER']:
                            # Text search in answer_text
                            filter_conditions &= Q(
                                event_question_answers__question=question,
                                event_question_answers__answer_text__icontains=question_value
                            )
                        elif question.question_type == 'BOOLEAN':
                            # Boolean matching
                            boolean_value = question_value.lower() in ['true', 'yes', '1']
                            filter_conditions &= Q(
                                event_question_answers__question=question,
                                event_question_answers__answer_text__iexact=str(boolean_value).lower()
                            )
                        elif question.question_type in ['CHOICE', 'MULTICHOICE']:
                            # Choice matching - check both selected choices and answer_text
                            filter_conditions &= Q(
                                event_question_answers__question=question
                            ) & (
                                Q(event_question_answers__selected_choices__text__icontains=question_value) |
                                Q(event_question_answers__selected_choices__value__icontains=question_value) |
                                Q(event_question_answers__answer_text__icontains=question_value)
                            )
                
                participants = participants.filter(filter_conditions).distinct()
            
            # Apply ordering
            if order_by == 'recent_updates':
                participants = participants.annotate(
                    latest_checkin=Max('user__event_attendance__check_in_time')
                ).order_by('-latest_checkin', '-registration_date')
            elif order_by == 'name':
                participants = participants.order_by('user__first_name', 'user__last_name')
            elif order_by == 'registration_date':
                participants = participants.order_by('-registration_date')
            
            # Get total count before pagination
            total_count = participants.count()
            
            # Calculate pagination
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            # Apply pagination
            paginated_participants = participants[start_index:end_index]
            
            # Collect filter options from all participants (not just paginated)
            all_participants = EventParticipant.objects.filter(event=event).select_related(
                'user__area_from__unit__chapter__cluster'
            )
            
            areas = set()
            chapters = set() 
            clusters = set()
            
            print(f"🔍 Collecting filter options from {all_participants.count()} participants")
            
            for p in all_participants:
                if hasattr(p.user, 'area_from') and p.user.area_from:
                    if p.user.area_from.area_name:
                        areas.add(p.user.area_from.area_name)
                    if hasattr(p.user.area_from, 'unit') and p.user.area_from.unit:
                        if hasattr(p.user.area_from.unit, 'chapter') and p.user.area_from.unit.chapter:
                            if p.user.area_from.unit.chapter.chapter_name:
                                chapters.add(p.user.area_from.unit.chapter.chapter_name)
                            if hasattr(p.user.area_from.unit.chapter, 'cluster') and p.user.area_from.unit.chapter.cluster:
                                if p.user.area_from.unit.chapter.cluster.cluster_id:
                                    clusters.add(p.user.area_from.unit.chapter.cluster.cluster_id)
            
            # Serialize participants using existing WebSocket serializer
            from apps.events.websocket_utils import serialize_participant_for_websocket
            participants_list = []
            for participant in paginated_participants:
                participant_data = serialize_participant_for_websocket(participant)
                participants_list.append(participant_data)
            
            return {
                'results': participants_list,
                'count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1,
                'filter_options': {
                    'areas': sorted(list(areas)),
                    'chapters': sorted(list(chapters)),
                    'clusters': sorted(list(clusters))
                }
            }
            
            print(f"🔍 Filter options collected - Areas: {len(areas)}, Chapters: {len(chapters)}, Clusters: {len(clusters)}")
            
            return result
        except Event.DoesNotExist:
            return {
                'results': [],
                'count': 0,
                'total_pages': 0,
                'has_next': False,
                'has_previous': False,
                'filter_options': {
                    'areas': [],
                    'chapters': [],
                    'clusters': []
                }
            }


class EventDashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for general event dashboard updates.
    Provides real-time updates for multiple events that user has access to.
    """

    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return

        # Create a user-specific group for dashboard updates
        self.dashboard_group_name = f'user_dashboard_{self.user.id}'

        # Join dashboard group
        await self.channel_layer.group_add(
            self.dashboard_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave dashboard group
        await self.channel_layer.group_discard(
            self.dashboard_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """
        Handle messages from WebSocket client
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            if message_type == 'get_events':
                await self.send_user_events()
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': text_data_json.get('timestamp')
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))

    async def event_update(self, event):
        """
        Handle general event update messages
        """
        await self.send(text_data=json.dumps({
            'type': 'event_update',
            'event_id': event['event_id'],
            'update_type': event['update_type'],
            'data': event['data'],
            'timestamp': event['timestamp']
        }))

    async def send_user_events(self):
        """
        Send list of events user has access to
        """
        events_data = await self.get_user_events()
        
        await self.send(text_data=json.dumps({
            'type': 'user_events',
            'events': events_data
        }))

    @database_sync_to_async
    def get_user_events(self):
        """
        Get events that user has access to monitor
        """
        from django.db import models
        
        events = Event.objects.filter(
            models.Q(created_by=self.user) |
            models.Q(service_team_members__user=self.user)
        ).distinct()
        
        events_list = []
        for event in events:
            # Get checked in count using EventDayAttendance model
            checked_in_count = EventDayAttendance.objects.filter(
                event=event,
                check_in_time__isnull=False,
                day_date=event.start_date.date() if event.start_date else None
            ).count()
            
            event_data = {
                'id': str(event.id),
                'name': event.name,
                'start_date': event.start_date.isoformat() if event.start_date else None,
                'end_date': event.end_date.isoformat() if event.end_date else None,
                'participant_count': EventParticipant.objects.filter(event=event).count(),
                'checked_in_count': checked_in_count
            }
            events_list.append(event_data)
        
        return events_list