from rest_framework import serializers
from events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop
)
from django.utils.translation import gettext_lazy as _

class EventRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventRole
        fields = '__all__'

class EventServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    role_names = serializers.SerializerMethodField()
    
    class Meta:
        model = EventServiceTeamMember
        fields = '__all__'
    
    def get_role_names(self, obj):
        return [role.get_role_name_display() for role in obj.roles.all()]

class EventSerializer(serializers.ModelSerializer):
    service_team_members = EventServiceTeamMemberSerializer(
        many=True, read_only=True
    )
    participants_count = serializers.IntegerField(
        source='participants.count', read_only=True
    )
    event_type_display = serializers.CharField(
        source='get_event_type_display', read_only=True
    )
    area_type_display = serializers.CharField(
        source='get_area_type_display', read_only=True
    )
    duration_days = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Event
        fields = '__all__'

class EventParticipantSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_ministry = serializers.CharField(source='user.ministry', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    participant_type_display = serializers.CharField(
        source='get_participant_type_display', read_only=True
    )
    
    class Meta:
        model = EventParticipant
        fields = '__all__'

class EventTalkSerializer(serializers.ModelSerializer):
    speaker_name = serializers.CharField(source='speaker.get_full_name', read_only=True)
    talk_type_display = serializers.CharField(
        source='get_talk_type_display', read_only=True
    )
    event_name = serializers.CharField(source='event.name', read_only=True)
    
    class Meta:
        model = EventTalk
        fields = '__all__'

class EventWorkshopSerializer(serializers.ModelSerializer):
    facilitator_names = serializers.SerializerMethodField()
    primary_facilitator_name = serializers.CharField(
        source='primary_facilitator.get_full_name', read_only=True
    )
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    event_name = serializers.CharField(source='event.name', read_only=True)
    current_participant_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = EventWorkshop
        fields = '__all__'
    
    def get_facilitator_names(self, obj):
        return [facilitator.get_full_name() for facilitator in obj.facilitators.all()]

class SimplifiedEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ('id', 'name', 'event_type', 'start_date', 'end_date')