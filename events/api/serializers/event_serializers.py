from rest_framework import serializers
from events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventResource,
    AreaLocation, EventVenue, SearchAreaSupportLocation
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from users.api.serializers import SimplifiedCommunityUserSerializer 
from .location_serializers import EventVenueSerializer

# TODO: create resources serializer, then to add a field onto the event serializer, for memo and extra resources attached to the event

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

class PublicEventResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventResource
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class SimplifiedEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(
        source='get_event_type_display', read_only=True
    )
    
    class Meta:
        model = Event
        fields = ('id', 'name', 'event_type', 'event_type_display', 'start_date', 'end_date')
        
class SimplifiedAreaLocationSerializer(serializers.ModelSerializer):
    # if you want to show unit + cluster names directly
    unit_name = serializers.CharField(source="unit.unit_name", read_only=True)
    cluster_name = serializers.CharField(source="unit.cluster.cluster_name", read_only=True)

    class Meta:
        model = AreaLocation
        fields = [
            "id", 
            "area_name",   # or whatever field you use in AreaLocation
            "unit_name",
            "cluster_name",
        ]
        
class EventSerializer(serializers.ModelSerializer):
    """
    Main event serializer
    """

    # Simplified service team info (just IDs for writes, details for reads)
    service_team_members = SimplifiedEventServiceTeamMemberSerializer(
        many=True, read_only=True, source="service_team"
    )

    # Supervisor details (read-only)
    youth_head = SimplifiedCommunityUserSerializer(
        source="supervising_chapter_youth_head", read_only=True
    )
    cfc_coordinator = SimplifiedCommunityUserSerializer(
        source="supervising_chapter_CFC_coordinator", read_only=True
    )

    # Statistics and display fields
    participants_count = serializers.IntegerField(
        source="participants.count", read_only=True
    )
    duration_days = serializers.SerializerMethodField(read_only=True)

    # Supervisors (write-only)
    supervising_chapter_youth_head = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    supervising_chapter_CFC_coordinator = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    # Location
    areas_involved = SimplifiedAreaLocationSerializer(many=True, read_only=True)

    # Venues
    venues = EventVenueSerializer(many=True, read_only=True)
    venue_ids = serializers.PrimaryKeyRelatedField(
        source="venues",
        queryset=EventVenue.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    # Resources
    resources = PublicEventResourceSerializer(many=True, read_only=True)
    memo = PublicEventResourceSerializer(read_only=True)
    memo_id = serializers.PrimaryKeyRelatedField(
        source="memo",
        queryset=EventResource.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "event_type",
            "event_code",
            "name",
            "name_code",
            "description",
            "sentence_description",
            "landing_image",
            "is_public",
            "start_date",
            "end_date",
            "duration_days",
            "area_type",
            "number_of_pax",
            "theme",
            "anchor_verse",
            "areas_involved",
            "venues",
            "venue_ids",
            "resources",
            "memo",
            "memo_id",
            "notes",
            # Participants / service team
            "participants_count",
            "service_team_members",
            "youth_head",
            "cfc_coordinator",
            # Write-only supervisor fields
            "supervising_chapter_youth_head",
            "supervising_chapter_CFC_coordinator",
        ]
        read_only_fields = [
            "id",
            "duration_days",
            "participants_count",
            "service_team_members",
            "youth_head",
            "cfc_coordinator",
            "resources",
            "memo",
        ]

    def get_duration_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        print(rep)
        return {
            "id": rep["id"],
            "basic_info": {
                "name": rep["name"],
                "name_code": rep["name_code"],
                "event_type": rep["event_type"],
                "event_code": rep["event_code"],
                "description": rep["description"],
                "sentence_description": rep["sentence_description"],
                "theme": rep["theme"],
                "anchor_verse": rep["anchor_verse"],
                "is_public": rep["is_public"],
                "landing_image": rep["landing_image"],
            },
            "dates": {
                "start_date": rep["start_date"],
                "end_date": rep["end_date"],
                "duration_days": rep["duration_days"],
            },
            "venue": {
                "venues": rep["venues"],
                "areas_involved": rep["areas_involved"],
            },
            "participants": {
                "participants_count": rep["participants_count"],
                "service_team_members": rep["service_team_members"],
                "youth_head": rep["youth_head"],
                "cfc_coordinator": rep["cfc_coordinator"],
            },
            "resources": {
                "memo": rep["memo"],
                "extra_resources": rep["resources"],
            },
            "notes": rep["notes"],
        }

    

class EventParticipantSerializer(serializers.ModelSerializer):
    '''
    Full detail Event participant serializer - for event organizers/admins
    '''
    user_details = SimplifiedCommunityUserSerializer(source="user", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    participant_type_display = serializers.CharField(
        source="get_participant_type_display", read_only=True
    )

    # Dates (output as datetime, but not writable by user)
    registered_on = serializers.DateTimeField(
        source="registration_date", read_only=True
    )
    confirmed_on = serializers.DateTimeField(
        source="confirmation_date", read_only=True
    )
    attended_on = serializers.DateTimeField(
        source="attended_date", read_only=True
    )
    class Meta:
        model = EventParticipant
        fields = [
            "user",
            "event",

            # Computed / display
            "user_details",
            "status",
            "status_display",
            "participant_type",
            "participant_type_display",

            # Dates
            "registered_on",
            "confirmed_on",
            "attended_on",

            # Writable user input
            "media_consent",
            "data_consent",
            "understood_registration",
            "dietary_restrictions",
            "special_needs",
            "emergency_contact",
            "emergency_phone",
            "notes",

            # Payment info
            "paid_amount",
            "payment_date",
            "verified",
        ]
        read_only_fields = [
            "id",
            "user_details",
            "status_display",
            "participant_type_display",
            "registered_on",
            "confirmed_on",
            "attended_on",
        ]