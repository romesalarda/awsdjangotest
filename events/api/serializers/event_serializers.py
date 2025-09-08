from rest_framework import serializers
from events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, GuestParticipant, EventResource,
    AreaLocation
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from users.api.serializers import SimplifiedCommunityUserSerializer  

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

# ! deprecated: remove model
# class GuestParticipantSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = GuestParticipant
#         fields = "__all__"
#         read_only_fields = ("id",)
        
#     def to_representation(self, instance):
#         rep = super().to_representation(instance)
#         return {
#             "id": rep["id"],
#             "personal_info": {
#                 "first_name": rep["first_name"],
#                 "last_name": rep["last_name"],
#                 "middle_name": rep["middle_name"],
#                 "preferred_name": rep["preferred_name"],
#                 "gender": rep["gender"],
#                 "date_of_birth": rep["date_of_birth"],
#                 "profile_picture": rep["profile_picture"],
#             },
#             "contact_info": {
#                 "email": rep["email"],
#                 "phone_number": rep["phone_number"],
#                 "emergency_contacts": rep["emergency_contacts"],
#             },
#             "location_info": {
#                 "outside_of_country": rep["outside_of_country"],
#                 "country_of_origin": rep["country_of_origin"],
#                 "chapter": rep["chapter"],
#             },
#             "event_info": {
#                 "event": rep["event"],
#                 "ministry_type": rep["ministry_type"],
#             },
#             "health_info": {
#                 "alergies": rep["alergies"],
#                 "further_alergy_information": rep["further_alergy_information"],
#             },
#         }

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
        
 # MAIN
class EventSerializer(serializers.ModelSerializer):
    '''
    Main event serializer
    '''
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

    duration_days = serializers.IntegerField(read_only=True)
    
    # For write operations, keep the original field names
    supervising_chapter_youth_head = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), write_only=True, required=False, allow_null=True
    )
    supervising_chapter_CFC_coordinator = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), write_only=True, required=False, allow_null=True
    )
    specific_area = SimplifiedAreaLocationSerializer()
    specific_area_id = serializers.PrimaryKeyRelatedField(
        source="specific_area",
        queryset=AreaLocation.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    
    resources = PublicEventResourceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Event
        fields = [
            'id', 'event_type','event_code', 'name', 'start_date', 'end_date', 'duration_days',
            'venue_address', 'venue_name', 'area_type', 'number_of_pax', 'theme',
            'anchor_verse', 'specific_area_id','specific_area', 'areas_involved',  # TODO add memo and resources
            
            # Read-only display fields
            'service_team_members', 'participants_count',
            'youth_head', 'cfc_coordinator', 'resources',
            
            # Write-only fields (keep original names for API consistency)
            'supervising_chapter_youth_head', 'supervising_chapter_CFC_coordinator'
        ]
        read_only_fields = [
            'service_team_members', 'participants_count',
            'duration_days', 'youth_head', 'cfc_coordinator'
        ]

    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {
            "id": rep["id"],
            "basic_info": {
                "name": rep["name"],
                "event_type": rep["event_type"],
                "event_code": rep["event_code"],
                "theme": rep["theme"],
                "anchor_verse": rep["anchor_verse"],
            },
            "dates": {
                "start_date": rep["start_date"],
                "end_date": rep["end_date"],
                "duration_days": rep["duration_days"],
            },
            "venue": {
                "venue_name": rep["venue_name"],
                "venue_address": rep["venue_address"],
                "specific_area": rep["specific_area"],
                "areas_involved": rep["areas_involved"],
            },
            "participants": {
                "participants_count": rep["participants_count"],
                "service_team_members": rep["service_team_members"],
                "youth_head": rep["youth_head"],
                "cfc_coordinator": rep["cfc_coordinator"],
            },
            "public-resources": rep["resources"],
        }
    
    # def get_specific_area(self, obj):
    #     return getattr(obj.specific_area, "area_id", None)

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