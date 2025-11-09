"""
Event Permission Utilities

This module provides helper functions for checking event-related permissions.
Supports hierarchical permission checking:
1. Event Creator - Full access
2. Event Heads - Full access
3. CFC Coordinators - Full access
4. Service Team Members - Based on ServiceTeamPermission
"""

from apps.events.models import Event, EventServiceTeamMember, ServiceTeamPermission
from apps.users.models import CommunityRole
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


def is_event_creator(user, event):
    """
    Check if user is the creator of the event.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user created the event
    """
    if isinstance(event, str):
        try:
            event = Event.objects.get(id=event)
        except Event.DoesNotExist:
            return False
    
    return event.created_by == user


def is_event_head(user, event):
    """
    Check if user is an event head (supervisor).
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user is an event head
    """
    if isinstance(event, str):
        try:
            event = Event.objects.get(id=event)
        except Event.DoesNotExist:
            return False
    
    # Check if user is in supervising_youth_heads
    if event.supervising_youth_heads.filter(id=user.id).exists():
        return True
    
    return False


def is_cfc_coordinator(user, event):
    """
    Check if user is a CFC coordinator for the event.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user is a CFC coordinator
    """
    if isinstance(event, str):
        try:
            event = Event.objects.get(id=event)
        except Event.DoesNotExist:
            return False
    
    # Check if user is in supervising_CFC_coordinators
    if event.supervising_CFC_coordinators.filter(id=user.id).exists():
        return True
    
    return False


def has_full_event_access(user, event):
    """
    Check if user has full access to the event (creator, event head, or CFC coordinator).
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user has full access
    """
    return (
        is_event_creator(user, event) or
        is_event_head(user, event) or
        is_cfc_coordinator(user, event)
    )


def can_manage_permissions(user, event):
    """
    Check if user can manage permissions for service team members.
    Only event creators, event heads, and CFC coordinators can manage permissions.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user can manage permissions
    """
    return has_full_event_access(user, event)


def get_user_event_permissions(user, event):
    """
    Get all permissions for a user on a specific event.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        dict: Dictionary of permission flags, or None if user has no access
        
    Example return:
    {
        'has_full_access': True/False,
        'can_view_participants': True/False,
        'can_edit_participants': True/False,
        ... (all permission flags)
    }
    """
    if isinstance(event, str):
        try:
            event = Event.objects.get(id=event)
        except Event.DoesNotExist:
            return None
    
    # Check if user has full access
    if has_full_event_access(user, event):
        return {
            'has_full_access': True,
            'is_creator': is_event_creator(user, event),
            'is_event_head': is_event_head(user, event),
            'is_cfc_coordinator': is_cfc_coordinator(user, event),
            'can_view_participants': True,
            'can_edit_participants': True,
            'can_remove_participants': True,
            'can_add_participants': True,
            'can_view_payments': True,
            'can_approve_payments': True,
            'can_process_refunds': True,
            'can_view_merch': True,
            'can_manage_merch': True,
            'can_approve_merch_payments': True,
            'can_access_checkin': True,
            'can_access_live_dashboard': True,
            'can_edit_event_details': True,
            'can_manage_service_team': True,
            'can_manage_permissions': True,
            'can_manage_resources': True,
            'can_manage_questions': True,
            'event_approved': event.approved,
            'can_approve': can_user_approve_event(user)
        }
    
    # Check if user is a service team member with specific permissions
    try:
        service_team_member = EventServiceTeamMember.objects.get(
            user=user,
            event=event
        )
        
        # Try to get permissions
        try:
            permissions = service_team_member.permissions
            return {
                'has_full_access': False,
                'is_creator': False,
                'is_event_head': False,
                'is_cfc_coordinator': False,
                'can_view_participants': permissions.can_view_participants,
                'can_edit_participants': permissions.can_edit_participants,
                'can_remove_participants': permissions.can_remove_participants,
                'can_add_participants': permissions.can_add_participants,
                'can_view_payments': permissions.can_view_payments,
                'can_approve_payments': permissions.can_approve_payments,
                'can_process_refunds': permissions.can_process_refunds,
                'can_view_merch': permissions.can_view_merch,
                'can_manage_merch': permissions.can_manage_merch,
                'can_approve_merch_payments': permissions.can_approve_merch_payments,
                'can_access_checkin': permissions.can_access_checkin,
                'can_access_live_dashboard': permissions.can_access_live_dashboard,
                'can_edit_event_details': permissions.can_edit_event_details,
                'can_manage_service_team': permissions.can_manage_service_team,
                'can_manage_permissions': permissions.can_manage_permissions,
                'can_manage_resources': permissions.can_manage_resources,
                'can_manage_questions': permissions.can_manage_questions,
                'event_approved': event.approved,
                'can_approve': can_user_approve_event(user)

            }
        except ServiceTeamPermission.DoesNotExist:
            # Service team member exists but no permissions set
            # Return all False
            return {
                'has_full_access': False,
                'is_creator': False,
                'is_event_head': False,
                'is_cfc_coordinator': False,
                'can_view_participants': False,
                'can_edit_participants': False,
                'can_remove_participants': False,
                'can_add_participants': False,
                'can_view_payments': False,
                'can_approve_payments': False,
                'can_process_refunds': False,
                'can_view_merch': False,
                'can_manage_merch': False,
                'can_approve_merch_payments': False,
                'can_access_checkin': False,
                'can_access_live_dashboard': False,
                'can_edit_event_details': False,
                'can_manage_service_team': False,
                'can_manage_permissions': False,
                'can_manage_resources': False,
                'can_manage_questions': False,
                'event_approved': event.approved,
                'can_approve': can_user_approve_event(user)

            }
    except EventServiceTeamMember.DoesNotExist:
        # User is not a service team member
        if can_user_approve_event(user):
            return {
                'has_full_access': False,
                'is_creator': False,
                'is_event_head': False,
                'is_cfc_coordinator': False,
                'can_view_participants': False,
                'can_edit_participants': False,
                'can_remove_participants': False,
                'can_add_participants': False,
                'can_view_payments': False,
                'can_approve_payments': False,
                'can_process_refunds': False,
                'can_view_merch': False,
                'can_manage_merch': False,
                'can_approve_merch_payments': False,
                'can_access_checkin': False,
                'can_access_live_dashboard': False,
                'can_edit_event_details': False,
                'can_manage_service_team': False,
                'can_manage_permissions': False,
                'can_manage_resources': False,
                'can_manage_questions': False,
                'event_approved': event.approved,
                'can_approve': True,

            }

        return None
    
        # TODO: add new permissions for community admins viewing event for approval
    
    


def has_event_permission(user, event, permission_name):
    """
    Check if user has a specific permission for an event.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        permission_name: str, name of the permission to check
        
    Returns:
        bool: True if user has the permission
        
    Example:
        has_event_permission(user, event, 'can_approve_payments')
    """
    permissions = get_user_event_permissions(user, event)
    
    if permissions is None:
        return False
    
    return permissions.get(permission_name, False)


def can_user_access_event_dashboard(user, event):
    """
    Check if user can access any part of the event dashboard.
    
    Args:
        user: CommunityUser instance
        event: Event instance or UUID
        
    Returns:
        bool: True if user has any dashboard access
    """
    permissions = get_user_event_permissions(user, event)
    
    if permissions is None:
        return False
    
    # User can access dashboard if they have any permission
    if permissions.get('has_full_access'):
        return True
    
    # Check if user has any specific permission
    return any([
        permissions.get('can_view_participants'),
        permissions.get('can_view_payments'),
        permissions.get('can_view_merch'),
        permissions.get('can_access_checkin'),
        permissions.get('can_access_live_dashboard'),
    ])

def can_user_approve_event(user):
    return user.community_roles.through.objects.filter(
            Q(role__role_name=CommunityRole.RoleType.COMMUNITY_ADMIN.name) |
            Q(role__role_name=CommunityRole.RoleType.EVENT_APPROVER.name)
        ).exists()