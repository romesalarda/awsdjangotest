import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.events.models import Event, EventParticipant, EventDayAttendance

User = get_user_model()


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
                await self.send_participants_data()
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
        
        await self.send(text_data=json.dumps({
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
        
        await self.send(text_data=json.dumps({
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
        
        await self.send(text_data=json.dumps({
            'type': 'initial_data',
            'event': event_data,
            'participants': participants_data
        }))

    async def send_participants_data(self):
        """
        Send current participants data
        """
        participants_data = await self.get_participants_data()
        
        await self.send(text_data=json.dumps({
            'type': 'participants_data',
            'participants': participants_data
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
    def get_participants_data(self):
        """
        Get current participants data with check-in status
        """
        try:
            event = Event.objects.get(id=self.event_id)
            participants = EventParticipant.objects.filter(event=event).select_related('user')
            
            participants_list = []
            for participant in participants:
                # Get latest attendance record for today - need to use EventDayAttendance model directly
                latest_attendance = EventDayAttendance.objects.filter(
                    event=participant.event,
                    user=participant.user,
                    day_date=participant.event.start_date.date() if participant.event.start_date else None
                ).first()
                
                participant_data = {
                    'id': str(participant.id),
                    'event_pax_id': participant.event_pax_id,
                    'user': {
                        'id': str(participant.user.id),
                        'first_name': participant.user.first_name,
                        'last_name': participant.user.last_name,
                        'email': participant.user.primary_email,
                    },
                    'status': participant.status,
                    'participant_type': participant.participant_type,
                    'registration_date': participant.registration_date.isoformat() if participant.registration_date else None,
                    'checked_in': latest_attendance.check_in_time is not None if latest_attendance else False,
                    'check_in_time': latest_attendance.check_in_time.isoformat() if latest_attendance and latest_attendance.check_in_time else None,
                    'check_out_time': latest_attendance.check_out_time.isoformat() if latest_attendance and latest_attendance.check_out_time else None,
                }
                participants_list.append(participant_data)
            
            return participants_list
        except Event.DoesNotExist:
            return []


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