from rest_framework import serializers
from apps.events.models import ServiceTeamPermission
from django.utils.translation import gettext_lazy as _
from apps.events.models import EventServiceTeamMember


class ServiceTeamPermissionSerializer(serializers.ModelSerializer):
    """
    Serializer for ServiceTeamPermission model.
    Handles both role-based and granular permission management.
    
    Example API object for ADMIN role:
    {
        "role": "ADMIN",
        "can_view_participants": true,
        "can_edit_participants": true,
        "can_remove_participants": true,
        "can_add_participants": true,
        "can_view_payments": true,
        "can_approve_payments": true,
        "can_process_refunds": true,
        "can_view_merch": true,
        "can_manage_merch": true,
        "can_approve_merch_payments": true,
        "can_access_checkin": true,
        "can_access_live_dashboard": true,
        "can_edit_event_details": true,
        "can_manage_service_team": true,
        "can_manage_permissions": true,
        "can_manage_resources": true,
        "can_manage_questions": true
    }
    
    Example API object for CUSTOM role with specific permissions:
    {
        "role": "CUSTOM",
        "can_view_participants": true,
        "can_edit_participants": false,
        "can_approve_payments": true,
        "can_view_merch": true,
        // ... other granular permissions
    }
    """
    
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    granted_by_name = serializers.SerializerMethodField(read_only=True)
    service_team_member_id = serializers.UUIDField(source='service_team_member.id', read_only=True)
    
    # Make service_team_member not required for updates (only required for creation)
    service_team_member = serializers.PrimaryKeyRelatedField(
        queryset=EventServiceTeamMember.objects.all(),  # Will be set in __init__
        required=False
    )
    
    class Meta:
        model = ServiceTeamPermission
        fields = [
            'id',
            'service_team_member',
            'service_team_member_id',
            'role',
            'role_display',
            
            # Participant management permissions
            'can_view_participants',
            'can_edit_participants',
            'can_remove_participants',
            'can_add_participants',
            
            # Payment management permissions
            'can_view_payments',
            'can_approve_payments',
            'can_process_refunds',
            
            # Merchandise management permissions
            'can_view_merch',
            'can_manage_merch',
            'can_approve_merch_payments',
            
            # Check-in & dashboard permissions
            'can_access_checkin',
            'can_access_live_dashboard',
            
            # Event management permissions
            'can_edit_event_details',
            'can_manage_service_team',
            'can_manage_permissions',
            
            # Resources & Q&A permissions
            'can_manage_resources',
            'can_manage_questions',
            
            # Metadata
            'created_at',
            'updated_at',
            'granted_by',
            'granted_by_name',
        ]
        read_only_fields = [
            'id',
            'service_team_member_id',
            'role_display',
            'created_at',
            'updated_at',
            'granted_by_name',
        ]
    
    def get_granted_by_name(self, obj):
        """Get the name of the user who granted these permissions."""
        if obj.granted_by:
            return f"{obj.granted_by.first_name} {obj.granted_by.last_name}".strip() or obj.granted_by.email
        return None
    
    def validate(self, attrs):
        """
        Custom validation to ensure permission consistency.
        """
        role = attrs.get('role', self.instance.role if self.instance else None)
        
        # If CUSTOM role, ensure at least one permission is granted
        if role == ServiceTeamPermission.PermissionRole.CUSTOM:
            has_permission = any([
                attrs.get(field, getattr(self.instance, field, False) if self.instance else False)
                for field in [
                    'can_view_participants', 'can_edit_participants', 'can_remove_participants',
                    'can_add_participants', 'can_view_payments', 'can_approve_payments',
                    'can_process_refunds', 'can_view_merch', 'can_manage_merch',
                    'can_approve_merch_payments', 'can_access_checkin', 'can_access_live_dashboard',
                    'can_edit_event_details', 'can_manage_service_team', 'can_manage_permissions',
                    'can_manage_resources', 'can_manage_questions'
                ]
            ])
            
            if not has_permission:
                raise serializers.ValidationError({
                    'role': _("CUSTOM role requires at least one permission to be granted.")
                })
        
        # Logical dependencies - if you can edit, you should be able to view
        if attrs.get('can_edit_participants') and not attrs.get('can_view_participants'):
            attrs['can_view_participants'] = True
        
        if attrs.get('can_manage_merch') and not attrs.get('can_view_merch'):
            attrs['can_view_merch'] = True
        
        if attrs.get('can_approve_payments') and not attrs.get('can_view_payments'):
            attrs['can_view_payments'] = True
        
        if attrs.get('can_approve_merch_payments') and not attrs.get('can_view_merch'):
            attrs['can_view_merch'] = True
        
        return attrs
    
    def create(self, validated_data):
        """
        Create a new permission record.
        The model's save method will auto-apply role template if needed.
        """
        # Set granted_by from request context if available
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['granted_by'] = request.user
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """
        Update an existing permission record.
        The model's save method will auto-apply role template if role changed.
        """
        # Update granted_by to track who made the change
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['granted_by'] = request.user
        
        return super().update(instance, validated_data)


class ServiceTeamPermissionSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for including permission info in service team member lists.
    Only includes the role and key permission flags.
    """
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = ServiceTeamPermission
        fields = [
            'role',
            'role_display',
            'can_view_participants',
            'can_edit_participants',
            'can_approve_payments',
            'can_manage_merch',
            'can_access_checkin',
            'can_access_live_dashboard',
            'can_manage_permissions',
        ]
        read_only_fields = fields


class ServiceTeamPermissionUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk permission updates via the service team member endpoint.
    Used when updating permissions as part of service team member update.
    """
    role = serializers.ChoiceField(
        choices=ServiceTeamPermission.PermissionRole.choices,
        required=False
    )
    
    # Participant management
    can_view_participants = serializers.BooleanField(required=False)
    can_edit_participants = serializers.BooleanField(required=False)
    can_remove_participants = serializers.BooleanField(required=False)
    can_add_participants = serializers.BooleanField(required=False)
    
    # Payment management
    can_view_payments = serializers.BooleanField(required=False)
    can_approve_payments = serializers.BooleanField(required=False)
    can_process_refunds = serializers.BooleanField(required=False)
    
    # Merchandise management
    can_view_merch = serializers.BooleanField(required=False)
    can_manage_merch = serializers.BooleanField(required=False)
    can_approve_merch_payments = serializers.BooleanField(required=False)
    
    # Check-in & dashboard
    can_access_checkin = serializers.BooleanField(required=False)
    can_access_live_dashboard = serializers.BooleanField(required=False)
    
    # Event management
    can_edit_event_details = serializers.BooleanField(required=False)
    can_manage_service_team = serializers.BooleanField(required=False)
    can_manage_permissions = serializers.BooleanField(required=False)
    
    # Resources & Q&A
    can_manage_resources = serializers.BooleanField(required=False)
    can_manage_questions = serializers.BooleanField(required=False)
