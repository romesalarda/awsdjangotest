from rest_framework import serializers
from events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from users.api.serializers import SimplifiedCommunityUserSerializer  # Assuming you have this

class EventRoleSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='get_role_name_display', read_only=True)
    
    class Meta:
        model = EventRole
        fields = ['id', 'role_name', 'display_name', 'description']
        read_only_fields = ['display_name']

class SimplifiedEventServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_details = SimplifiedCommunityUserSerializer(source='user', read_only=True)
    role_names = serializers.SerializerMethodField()
    
    class Meta:
        model = EventServiceTeamMember
        fields = ['id', 'user_details', 'role_names', 'head_of_role', 'assigned_at']
    
    def get_role_names(self, obj):
        return [role.get_role_name_display() for role in obj.roles.all()]

class EventServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_details = SimplifiedCommunityUserSerializer(source='user', read_only=True)
    role_details = EventRoleSerializer(source='roles', many=True, read_only=True)
    
    class Meta:
        model = EventServiceTeamMember
        fields = '__all__'

class EventSerializer(serializers.ModelSerializer):
    # Simplified service team info (just IDs for writes, details for reads)
    service_team_members = SimplifiedEventServiceTeamMemberSerializer(
        many=True, read_only=True
    )
    
    # Supervisor details (read-only)
    youth_head = SimplifiedCommunityUserSerializer(
        source='supervising_chapter_youth_head', read_only=True
    )
    cfc_coordinator = SimplifiedCommunityUserSerializer(
        source='supervising_chapter_CFC_coordinator', read_only=True
    )
    
    # Statistics and display fields
    participants_count = serializers.IntegerField(
        source='participants.count', read_only=True
    )
    # event_type_display = serializers.CharField(
    #     source='get_event_type_display', read_only=True
    # )
    # area_type_display = serializers.CharField(
    #     source='get_area_type_display', read_only=True
    # )
    duration_days = serializers.IntegerField(read_only=True)
    
    # For write operations, keep the original field names
    supervising_chapter_youth_head = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), write_only=True, required=False, allow_null=True
    )
    supervising_chapter_CFC_coordinator = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), write_only=True, required=False, allow_null=True
    )
    specific_area = serializers.CharField(source="specific_area.area_id")
    
    class Meta:
        model = Event
        fields = [
            'id', 'event_type', 'name', 'start_date', 'end_date', 'duration_days',
            'venue_address', 'venue_name', 'area_type', 'number_of_pax', 'theme',
            'anchor_verse', 'specific_area', 'areas_involved',
            
            # Read-only display fields
            'service_team_members', 'participants_count',
            'youth_head', 'cfc_coordinator',
            
            # Write-only fields (keep original names for API consistency)
            'supervising_chapter_youth_head', 'supervising_chapter_CFC_coordinator'
        ]
        read_only_fields = [
            'service_team_members', 'participants_count',
            'duration_days', 'youth_head', 'cfc_coordinator'
        ]

    def to_representation(self, instance):
        """Custom representation to clean up the output"""
        representation = super().to_representation(instance)
        
        # Remove the write-only fields from the response
        representation.pop('supervising_chapter_youth_head', None)
        representation.pop('supervising_chapter_CFC_coordinator', None)
        
        return representation

class EventParticipantSerializer(serializers.ModelSerializer):
    user_details = SimplifiedCommunityUserSerializer(source='user', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    participant_type_display = serializers.CharField(
        source='get_participant_type_display', read_only=True
    )
    
    class Meta:
        model = EventParticipant
        fields = '__all__'
        read_only_fields = ['registration_date', 'confirmation_date', 'attended_date']

class EventTalkSerializer(serializers.ModelSerializer):
    speaker_details = SimplifiedCommunityUserSerializer(source='speaker', read_only=True)
    talk_type_display = serializers.CharField(
        source='get_talk_type_display', read_only=True
    )
    event_name = serializers.CharField(source='event.name', read_only=True)
    
    class Meta:
        model = EventTalk
        fields = '__all__'

class EventWorkshopSerializer(serializers.ModelSerializer):
    facilitator_details = SimplifiedCommunityUserSerializer(
        source='facilitators', many=True, read_only=True
    )
    primary_facilitator_details = SimplifiedCommunityUserSerializer(
        source='primary_facilitator', read_only=True
    )
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    current_participant_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = EventWorkshop
        fields = '__all__'

class SimplifiedEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(
        source='get_event_type_display', read_only=True
    )
    
    class Meta:
        model = Event
        fields = ('id', 'name', 'event_type', 'event_type_display', 'start_date', 'end_date')