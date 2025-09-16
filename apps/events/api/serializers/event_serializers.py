from rest_framework import serializers
from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventResource,
    AreaLocation, EventVenue
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from apps.events.models import EventDayAttendance
from apps.users.api.serializers import SimpleEmergencyContactSerializer, SimplifiedCommunityUserSerializer, SimpleAllergySerializer, SimpleMedicalConditionSerializer
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
    # role_names = serializers.SerializerMethodField()
    
    class Meta:
        model = EventServiceTeamMember
        fields = ['id', 'user_details', 'head_of_role', 'assigned_at']
    
    # def get_role_names(self, obj):
    #     return [role.get_role_name_display() for role in obj.roles.all()]

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
    
    name = serializers.CharField(required=True)
    
    class Meta:
        model = Event
        fields = (
            "event_type",
            "event_code",
            "name",
            "sentence_description",
            "landing_image",
            "start_date",
            "end_date",
            "duration_days",
            "area_type",
            "theme",
            "anchor_verse",
        )
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {
            "identity": {
                "event_type": rep["event_type"],
                "event_code": rep["event_code"],
                "name": rep["name"],
                "description": rep["sentence_description"],
                "theme": rep.get("theme"),
                "anchor_verse": rep.get("anchor_verse")
            },
            "media": {
                "landing_image": rep.get("landing_image")
            },
            "timing": {
                "start_date": rep.get("start_date"),
                "end_date": rep.get("end_date"),
                "duration_days": rep.get("duration_days")
            },
            "location": {
                "area_type": rep.get("area_type")
            }
        }
        
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
    
    name = serializers.CharField(required=True)

    # Simplified service team info (just IDs for writes, details for reads)
    service_team_members = SimplifiedEventServiceTeamMemberSerializer(
        many=True, read_only=True, source="service_team"
    )

    # Supervisor details (read-only)
    supervising_youth_heads = SimplifiedCommunityUserSerializer(
        read_only=True, many=True
    )
    supervising_CFC_coordinators = SimplifiedCommunityUserSerializer(
        read_only=True, many=True
    )

    # Statistics and display fields
    participants_count = serializers.IntegerField(
        source="participants.count", read_only=True
    )
    duration_days = serializers.SerializerMethodField(read_only=True)
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
            # Write-only supervisor fields
            "supervising_youth_heads",
            "supervising_CFC_coordinators",
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
            "people": {
                "participants_count": rep["participants_count"],
                "service_team_members": rep["service_team_members"],
                "event_heads": rep["supervising_youth_heads"],
                "cfc_coordinators": rep["supervising_CFC_coordinators"],
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
    event = serializers.CharField(source="event.event_code", read_only=True)
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
    dietary_restrictions = SimpleAllergySerializer(
        source="user.user_allergies", many=True, read_only=True
    )
    emergency_contacts = SimpleEmergencyContactSerializer(
        source="user.community_user_emergency_contacts", many=True, read_only=True
    )
    medical_conditions = SimpleMedicalConditionSerializer(
        source="user.user_medical_conditions", many=True, read_only=True
    )

    class Meta:
        model = EventParticipant
        fields = [
            "event",
            "user_details",
            "status",
            "status_display",
            "participant_type",
            "participant_type_display",
            "registered_on",
            "confirmed_on",
            "attended_on",
            "media_consent",
            "data_consent",
            "understood_registration",
            "dietary_restrictions",
            "special_needs",
            "emergency_contacts",
            "medical_conditions",
            "notes",
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

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {
            "event": rep["event"],
            "user": rep["user_details"],
            "status": {
                "code": rep["status"],
                "participant_type": rep["participant_type"],
            },
            "dates": {
                "registered_on": rep["registered_on"],
                "confirmed_on": rep["confirmed_on"],
                "attended_on": rep["attended_on"],
                "payment_date": rep["payment_date"],
            },
            "consents": {
                "media_consent": rep["media_consent"],
                "data_consent": rep["data_consent"],
                "understood_registration": rep["understood_registration"],
            },
            "health": {
                "dietary_restrictions": rep["dietary_restrictions"],
                "medical_conditions": rep["medical_conditions"],
                "special_needs": rep["special_needs"],
            },
            "emergency_contacts": rep["emergency_contacts"],
            "notes": rep["notes"],
            "payment": {
                "paid_amount": rep["paid_amount"],
                "verified": rep["verified"],
            },
        }
        
class SimplifiedEventParticipantSerializer(serializers.ModelSerializer):
    """
    Flat, minimal participant info for table/list views.
    """
    event = serializers.CharField(source="event.event_code", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    registration_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = EventParticipant
        fields = [
            "event_pax_id",
            "event",  # UUID of event
            "user",   # UUID of user
            "first_name",
            "last_name",
            "email",
            "participant_type",
            "status",
            "registration_date",
        ]
        read_only_fields = fields
        
class EventDayAttendanceSerializer(serializers.ModelSerializer):
    user_details = SimplifiedCommunityUserSerializer(source="user", read_only=True)
    event_code = serializers.CharField(source="event.event_code", read_only=True)
    duration = serializers.DurationField(read_only=True)

    class Meta:
        model = EventDayAttendance
        fields = [
            "id",
            "event",
            "event_code",
            "user",
            "user_details",
            "day_date",
            "day_id",
            "check_in_time",
            "check_out_time",
            "duration",
        ]
        read_only_fields = ["id", "duration", "event_code", "user_details"]