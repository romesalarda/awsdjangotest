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
                check_in_time = latest_check_in_time.isoformat()
            if latest_check_out_time:
                check_out_time = latest_check_out_time.isoformat()
        
        # Serialize all attendance records
        attendance_records = []
        for attendance in all_attendance:
            attendance_records.append({
                'id': str(attendance.id),
                'day_date': attendance.day_date.isoformat() if attendance.day_date else None,
                'check_in_time': attendance.check_in_time.isoformat() if attendance.check_in_time else None,
                'check_out_time': attendance.check_out_time.isoformat() if attendance.check_out_time else None,
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
            # Convert amount from pence to pounds for display
            amount_pounds = float(payment.amount) / 100 if payment.amount else 0
            
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
                'price_at_purchase': order.price_at_purchase if order.price_at_purchase else 0,
                'discount_applied': order.discount_applied if order.discount_applied else 0,
                'status': order.status,
                'changeable': order.changeable,
                'change_requested': order.change_requested,
                'change_reason': order.change_reason,
                'added': order.added.isoformat() if order.added else None,
            }
            product_orders_data.append(order_info)
        
        print(f"🛒 SERIALIZE - Final product orders data for {participant.user.first_name}: {len(product_orders_data)} orders")
        if product_orders_data:
            print(f"🛒 SERIALIZE - Sample order: {product_orders_data[0]}")

        serialized_data = {
            'id': str(participant.id),
            'event_pax_id': participant.event_pax_id,
            'user': {
                'id': str(participant.user.id),
                'first_name': participant.user.first_name,
                'last_name': participant.user.last_name,
                'email': getattr(participant.user, 'email', None) or getattr(participant.user, 'primary_email', None),
                'phone': getattr(participant.user, 'phone', None),
                'profile_picture': participant.user.profile_picture.url if hasattr(participant.user, 'profile_picture') and participant.user.profile_picture else None,
                'area_from_display': {
                    'area': getattr(getattr(participant.user, 'area_from_display', None), 'area', None)
                } if hasattr(participant.user, 'area_from_display') and getattr(participant.user, 'area_from_display', None) else None,
            },
            'status': {
                'code': participant.status,
                'display_name': participant.get_status_display(),
            } if participant.status else None,
            'participant_type': {
                'code': participant.participant_type,
                'display_name': participant.get_participant_type_display(),
            } if participant.participant_type else None,
            'registration_date': participant.registration_date.isoformat() if participant.registration_date else None,
            'checked_in': is_currently_checked_in,
            'check_status': current_status,  # New field for 3-status system
            'check_in_time': check_in_time,
            'check_out_time': check_out_time,
            'attendance_records': attendance_records,  # All attendance history
            'has_payment_issues': has_payment_issues,
            'total_outstanding': total_outstanding,
            'event_payments': payment_data,
            'product_orders': product_orders_data,  # Product orders
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