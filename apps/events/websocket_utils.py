from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
import pytz


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
        
        # Get all attendance records for this participant
        from apps.events.models import EventDayAttendance
        from datetime import date
        
        all_attendance = EventDayAttendance.objects.filter(
            event=participant.event,
            user=participant.user
        ).order_by('-day_date', '-check_in_time')
        
        print(f"📅 SERIALIZING - Found {all_attendance.count()} attendance records")
        
        # Determine current status based on latest attendance
        current_status = 'not-checked-in'  # Default
        is_currently_checked_in = False
        check_in_time = None
        check_out_time = None
        
        if all_attendance.exists():
            latest_attendance = all_attendance.first()
            latest_check_in_time = latest_attendance.check_in_time
            latest_check_out_time = latest_attendance.check_out_time
            
            if latest_check_in_time and latest_check_out_time:
                current_status = 'checked-out'
                is_currently_checked_in = False
            elif latest_check_in_time:
                current_status = 'checked-in'
                is_currently_checked_in = True
            
            print(f"📊 SERIALIZING - Check-in status: {current_status}")
            
            if latest_check_in_time:
                london_check_in = convert_to_london_time(latest_check_in_time)
                check_in_time = str(london_check_in) if london_check_in else None
            if latest_check_out_time:
                london_check_out = convert_to_london_time(latest_check_out_time)
                check_out_time = str(london_check_out) if london_check_out else None
        
        # Serialize all attendance records
        attendance_records = []
        for attendance in all_attendance:
            london_check_in = convert_to_london_time(attendance.check_in_time)
            london_check_out = convert_to_london_time(attendance.check_out_time)
            
            attendance_records.append({
                'id': str(attendance.id),
                'day_date': attendance.day_date.isoformat() if attendance.day_date else None,
                'check_in_time': str(london_check_in) if london_check_in else None,
                'check_out_time': str(london_check_out) if london_check_out else None,
                'day_id': attendance.day_id,
            })
        
        # Get payment information for priority sorting
        from apps.events.models import EventPayment
        event_payments = EventPayment.objects.filter(
            user=participant,  # EventPayment.user is a ForeignKey to EventParticipant
            event=participant.event
        )
        
        has_payment_issues = False
        total_outstanding = 0
        payment_data = []
        
        for payment in event_payments:
            # Convert DecimalField to float for JSON serialization
            amount_pounds = float(payment.amount) if payment.amount else 0.0
            
            # Calculate outstanding amount: full amount if pending/failed, 0 if succeeded
            outstanding_amount = 0
            if payment.status in ['PENDING', 'FAILED']:
                outstanding_amount = amount_pounds
                has_payment_issues = True
                total_outstanding += amount_pounds
            
            payment_info = {
                'id': payment.id,
                'amount': amount_pounds,
                'booking_price': amount_pounds,  # For backwards compatibility
                'payment_status': payment.status,
                'bank_reference': payment.bank_reference,
                'outstanding_amount': outstanding_amount,
                'currency': payment.currency,
                'verified': payment.verified,
            }
            payment_data.append(payment_info)

        # Get product orders for this participant through cart->user relationship
        from apps.shop.models import EventProductOrder, EventCart
        
        # Debug: Check if user has any carts for this event
        user_carts = EventCart.objects.filter(user=participant.user, event=participant.event)
        print(f"🛒 SERIALIZE - User {participant.user.first_name} has {user_carts.count()} carts for event {participant.event.id}")
        
        product_orders = EventProductOrder.objects.filter(
            cart__user=participant.user,
            cart__event=participant.event
        ).select_related('product', 'size', 'cart').order_by('-added')
        
        product_orders_data = []
        for order in product_orders:
            order_info = {
                'id': str(order.id),
                'order_reference_id': order.order_reference_id,
                'product_name': order.product.title if order.product else None,
                'size': order.size.size if order.size else None,
                'quantity': order.quantity,
                'price_at_purchase': float(order.price_at_purchase) if order.price_at_purchase else 0.0,
                'discount_applied': float(order.discount_applied) if order.discount_applied else 0.0,
                'status': order.status,
                'changeable': order.changeable,
                'change_requested': order.change_requested,
                'change_reason': order.change_reason,
                'added': convert_to_london_time(order.added).isoformat() if order.added else None,
            }
            product_orders_data.append(order_info)
        
        print(f"🛒 SERIALIZE - Final product orders data for {participant.user.first_name}: {len(product_orders_data)} orders")
        if product_orders_data:
            print(f"🛒 SERIALIZE - Sample order: {product_orders_data[0]}")

        # Build area_from_display to match REST API structure
        area_from_display = None
        try:
            if hasattr(participant.user, 'area_from') and participant.user.area_from:
                area = participant.user.area_from
                cluster_info = None
                chapter_info = None
                if hasattr(area, 'unit') and area.unit:
                    chapter_info = getattr(area.unit.chapter, 'chapter_name', None) if hasattr(area.unit, 'chapter') else None
                    cluster_info = getattr(area.unit.chapter.cluster, 'cluster_id', None) if (hasattr(area.unit, 'chapter') and hasattr(area.unit.chapter, 'cluster')) else None
                area_from_display = {
                    "area": getattr(area, 'area_name', None),
                    "chapter": chapter_info,
                    "cluster": cluster_info,
                }
            else:
                area_from_display = {"area": None, "chapter": None, "cluster": None}
        except AttributeError:
            area_from_display = None

        # Match ParticipantManagementSerializer structure exactly
        serialized_data = {
            'event': participant.event.event_code,
            'event_user_id': participant.event_pax_id,
            'user': {
                "first_name": participant.user.first_name,
                "last_name": participant.user.last_name,
                "ministry": getattr(participant.user, 'ministry', None),
                "gender": getattr(participant.user, 'gender', None),
                "date_of_birth": getattr(participant.user, 'date_of_birth', None),
                "member_id": getattr(participant.user, 'member_id', None),
                "username": participant.user.username,
                "profile_picture": participant.user.profile_picture.url if hasattr(participant.user, 'profile_picture') and participant.user.profile_picture else None,
                "area_from_display": area_from_display,
                "primary_email": getattr(participant.user, 'primary_email', None),
                "phone": getattr(participant.user, 'phone_number', None),
            },
            'status': {
                "code": participant.status,
                "participant_type": participant.participant_type,
            },
            'dates': {
                "registered_on": participant.registration_date,
                "confirmed_on": participant.confirmation_date,
                "attended_on": participant.attended_date,
                "payment_date": participant.payment_date,
            },
            'consents': {
                "media_consent": participant.media_consent,
                "data_consent": participant.data_consent,
                "understood_registration": participant.understood_registration,
            },
            'health': {
                "allergies": [],  # Simplified for WebSocket
                "medical_conditions": [],
            },
            'emergency_contacts': [],  # Simplified for WebSocket
            'notes': participant.notes,
            'payment': {
                "paid_amount": str(participant.paid_amount),
            },
            'verified': participant.verified,
            'event_payments': payment_data,
            'carts': [],  # Simplified for WebSocket
            'questions_answered': [],  # Simplified for WebSocket
            'checked_in': is_currently_checked_in,
            'check_status': current_status,
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
            'attendance_records': attendance_records,
            'product_orders': product_orders_data,
        }
        
        print(f"✅ SERIALIZING SUCCESS - Data: {serialized_data['user']['first_name']} is checked_in: {serialized_data['checked_in']}")
        
        # Test JSON serialization to catch any remaining issues
        try:
            json.dumps(serialized_data, cls=DjangoJSONEncoder)
        except Exception as json_error:
            print(f"🚨 JSON SERIALIZATION TEST FAILED - Error: {json_error}")
            print(f"🚨 Problematic data: {serialized_data}")
            raise
        
        return serialized_data
        
    except Exception as e:
        print(f"❌ SERIALIZING FAILED - Error: {e}")
        print(f"❌ SERIALIZING FAILED - Participant: {participant}")
        print(f"❌ SERIALIZING FAILED - Participant User: {participant.user}")
        print(f"❌ SERIALIZING FAILED - Participant Event: {participant.event}")
        
        # Create minimal safe serialization for error cases
        try:
            minimal_data = {
                'id': str(participant.id),
                'event_pax_id': getattr(participant, 'event_pax_id', None),
                'user': {
                    'id': str(participant.user.id),
                    'first_name': getattr(participant.user, 'first_name', 'Unknown'),
                    'last_name': getattr(participant.user, 'last_name', 'Unknown'),
                    'email': None,
                    'phone': None,
                    'profile_picture': None,
                    'area_from_display': None,
                },
                'status': None,
                'participant_type': None,
                'registration_date': None,
                'checked_in': False,
                'check_in_time': None,
                'check_out_time': None,
                'has_payment_issues': False,
                'total_outstanding': 0,
                'event_payments': [],
            }
            print(f"🔄 USING MINIMAL SERIALIZATION for participant: {participant.id}")
            return minimal_data
        except Exception as minimal_error:
            print(f"❌ EVEN MINIMAL SERIALIZATION FAILED - Error: {minimal_error}")
            raise e


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