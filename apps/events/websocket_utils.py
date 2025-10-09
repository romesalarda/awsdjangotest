from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder


class WebSocketNotifier:
    """
    Utility class for sending WebSocket notifications to event groups
    """
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def notify_checkin_update(self, event_id, participant_data, action='checkin'):
        """
        Send check-in update to all connected clients monitoring this event
        
        Args:
            event_id (str/UUID): The event ID
            participant_data (dict): Participant information
            action (str): 'checkin' or 'checkout'
        """
        participant_name = participant_data.get('user', {}).get('first_name', 'Unknown')
        print(f"🚀 NOTIFY_CHECKIN_UPDATE - Event ID: {event_id}, Participant: {participant_name}, Action: {action}")
        
        if not self.channel_layer:
            print(f"❌ NOTIFY_CHECKIN_UPDATE FAILED - No channel layer available")
            return
        
        event_group_name = f'event_checkin_{event_id}'
        print(f"📡 NOTIFY_CHECKIN_UPDATE - Sending to group: {event_group_name}")
        
        message = {
            'type': 'checkin_update',
            'participant': participant_data,
            'action': action,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            async_to_sync(self.channel_layer.group_send)(
                event_group_name,
                message
            )
            print(f"✅ NOTIFY_CHECKIN_UPDATE SUCCESS - Sent to group {event_group_name}")
        except Exception as e:
            print(f"❌ NOTIFY_CHECKIN_UPDATE FAILED - Error: {e}")
            raise
    
    def notify_participant_registered(self, event_id, participant_data):
        """
        Send new participant registration notification
        
        Args:
            event_id (str/UUID): The event ID
            participant_data (dict): Participant information
        """
        if not self.channel_layer:
            return
        
        event_group_name = f'event_checkin_{event_id}'
        
        message = {
            'type': 'participant_registered',
            'participant': participant_data,
            'timestamp': datetime.now().isoformat()
        }
        
        async_to_sync(self.channel_layer.group_send)(
            event_group_name,
            message
        )
    
    def notify_event_update(self, user_ids, event_id, update_type, data):
        """
        Send event update to specific users' dashboard
        
        Args:
            user_ids (list): List of user IDs to notify
            event_id (str/UUID): The event ID
            update_type (str): Type of update (e.g., 'participant_count_changed')
            data (dict): Update data
        """
        if not self.channel_layer:
            return
        
        for user_id in user_ids:
            dashboard_group_name = f'user_dashboard_{user_id}'
            
            message = {
                'type': 'event_update',
                'event_id': str(event_id),
                'update_type': update_type,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            
            async_to_sync(self.channel_layer.group_send)(
                dashboard_group_name,
                message
            )


# Global instance for easy access
websocket_notifier = WebSocketNotifier()


def serialize_participant_for_websocket(participant):
    """
    Serialize participant data for WebSocket transmission
    
    Args:
        participant: EventParticipant instance
    
    Returns:
        dict: Serialized participant data
    """
    try:
        print(f"🔄 SERIALIZING participant: {participant.user.first_name} {participant.user.last_name} (ID: {participant.id})")
        
        # Get the most recent day attendance for that event
        from apps.events.models import EventDayAttendance
        from datetime import date
        
        latest_attendance = EventDayAttendance.objects.filter(
            event=participant.event,
            user=participant.user
        ).order_by('-day_date', '-id').first()
        
        print(f"📅 SERIALIZING - Latest attendance: {latest_attendance}")
        
        # Check if person is currently checked in:
        # 1. Must have a check_in_time
        # 2. Must NOT have a check_out_time (attendance is not stale/complete)
        is_currently_checked_in = False
        check_in_time = None
        check_out_time = None
        
        if latest_attendance:
            has_check_in = latest_attendance.check_in_time is not None
            has_check_out = latest_attendance.check_out_time is not None
            
            # Person is checked in if they have check-in time but no check-out time
            is_currently_checked_in = has_check_in and not has_check_out
            
            print(f"📊 SERIALIZING - Check-in status:")
            print(f"   - Has check-in time: {has_check_in}")
            print(f"   - Has check-out time: {has_check_out}")
            print(f"   - Currently checked in: {is_currently_checked_in}")
            
            if latest_attendance.check_in_time:
                check_in_time = latest_attendance.check_in_time.isoformat()
            if latest_attendance.check_out_time:
                check_out_time = latest_attendance.check_out_time.isoformat()
        
        serialized_data = {
            'id': str(participant.id),
            'event_pax_id': participant.event_pax_id,
            'user': {
                'id': str(participant.user.id),
                'first_name': participant.user.first_name,
                'last_name': participant.user.last_name,
                'email': participant.user.primary_email ,
            },
            'status': participant.status,
            'participant_type': participant.participant_type,
            'registration_date': participant.registration_date.isoformat() if participant.registration_date else None,
            'checked_in': is_currently_checked_in,
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
        }
        
        print(f"✅ SERIALIZING SUCCESS - Data: {serialized_data['user']['first_name']} is checked_in: {serialized_data['checked_in']}")
        return serialized_data
        
    except Exception as e:
        print(f"❌ SERIALIZING FAILED - Error: {e}")
        print(f"❌ SERIALIZING FAILED - Participant: {participant}")
        raise


def get_event_supervisors(event):
    """
    Get list of user IDs who should receive event updates
    
    Args:
        event: Event instance
    
    Returns:
        list: List of user IDs
    """
    user_ids = []
    
    print(f"🔍 GET_EVENT_SUPERVISORS - Event: {event.name} (ID: {event.id})")
    
    # Add event creator
    if event.created_by:
        user_ids.append(event.created_by.id)
        print(f"👤 GET_EVENT_SUPERVISORS - Added event creator: {event.created_by.username} (ID: {event.created_by.id})")
    else:
        print(f"⚠️ GET_EVENT_SUPERVISORS - No event creator found")
    
    # Add service team members
    service_team_users = event.service_team_members.values_list('user_id', flat=True)
    user_ids.extend(service_team_users)
    print(f"👥 GET_EVENT_SUPERVISORS - Added {len(service_team_users)} service team members: {list(service_team_users)}")
    
    final_user_ids = list(set(user_ids))  # Remove duplicates
    print(f"📋 GET_EVENT_SUPERVISORS - Final supervisor IDs: {final_user_ids}")
    
    return final_user_ids