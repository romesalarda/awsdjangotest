from rest_framework import serializers
from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventResource, ParticipantQuestion,
    AreaLocation, EventVenue
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import get_list_or_404, get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError

import pprint

from apps.events.models import (
    EventDayAttendance, QuestionAnswer, ParticipantQuestion,
    EventServiceTeamMember, EventPaymentMethod, EventPaymentPackage, EventPayment
    )
from apps.users.api.serializers import (
    SimpleEmergencyContactSerializer, SimplifiedCommunityUserSerializer, 
    SimpleAllergySerializer, SimpleMedicalConditionSerializer,
)
from apps.users.models import CommunityUser, MedicalCondition, Allergy, EmergencyContact
from .location_serializers import EventVenueSerializer, AreaLocationSerializer
from .registration_serializers import ExtraQuestionSerializer, QuestionAnswerSerializer, QuestionChoiceSerializer
from .payment_serializers import EventPaymentPackageSerializer, EventPaymentMethodSerializer, EventPaymentSerializer

from apps.shop.api import serializers as shop_serializers
from apps.shop import models as shop_models

class EventRoleSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='get_role_name_display', read_only=True)
    
    class Meta:
        model = EventRole
        fields = ['id', 'role_name', 'display_name', 'description']
        read_only_fields = ['display_name']

class SimplifiedEventServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_details = SimplifiedCommunityUserSerializer(source='user', read_only=True)
    
    class Meta:
        model = EventServiceTeamMember
        fields = ['id', 'user_details', 'head_of_role', 'assigned_at']

class EventServiceTeamMemberSerializer(serializers.ModelSerializer):
    '''
    Full detail Event service team member serializer - for event organizers/admins
    '''
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
    '''
    Event workshop serializer
    '''
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
    '''
    Simplified event serializer for dropdowns, lists, etc
    '''
    name = serializers.CharField(required=True)    
    # only get the name of the area and not the full serializer
    areas_involved = serializers.SerializerMethodField(read_only=True)
    main_venue = serializers.SerializerMethodField(read_only=True)
    cost = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Event
        fields = (
            "id",
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
            "areas_involved",
            "main_venue",
            "registration_open",
            "cost",
        )
        
    def get_main_venue(self, obj):
        primary_venue = obj.venues.filter(Q(primary_venue=True) | Q(venue_type=EventVenue.VenueType.MAIN_VENUE)).first()
        if primary_venue:
            return primary_venue.name
        return None
        
    def get_cost(self, obj):
        packages = obj.payment_packages.all().order_by("price")
        if packages.exists():
            pkg = packages.first()
            if pkg.price == 0:
                return "Free"
            pkg_text = f"{pkg.currency.upper()} {pkg.price}"
            if len(packages) > 1:
                pkg_text = pkg_text + "+"
            return pkg_text
        
    def get_areas_involved(self, obj):
        return [area.area_name for area in obj.areas_involved.all()]
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {
            "identity": {
                "id": rep["id"],
                "event_type": rep["event_type"],
                "event_code": rep["event_code"],
                "name": rep["name"],
                "description": rep["sentence_description"],
                "theme": rep.get("theme"),
                "anchor_verse": rep.get("anchor_verse"),
                "cost": rep.get("cost")
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
                "area_type": rep.get("area_type"),
                "areas_involved": rep.get("areas_involved"),
                "main_venue": rep.get("main_venue"),
            }
        }


class UserAwareEventSerializer(SimplifiedEventSerializer):
    '''
    Enhanced event serializer that includes user-specific information like registration status and organizer permissions
    '''
    user_registration_status = serializers.SerializerMethodField(read_only=True)
    is_user_organizer = serializers.SerializerMethodField(read_only=True)
    
    class Meta(SimplifiedEventSerializer.Meta):
        fields = list(SimplifiedEventSerializer.Meta.fields) + [
            "user_registration_status",
            "is_user_organizer"
        ]
    
    def get_user_registration_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
            
        participant = obj.participants.filter(user=request.user).first()
        if participant:
            return participant.status
        return None
        
    def get_is_user_organizer(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
            
        # Check if user is the creator of the event
        if obj.created_by == request.user:
            return True
            
        # Check if user is a service team member
        if obj.service_team_members.filter(user=request.user).exists():
            return True
            
        # Check if user has encoder permissions (can manage events)
        if hasattr(request.user, 'community') and request.user.community.encoder:
            return True
            
        return False
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Add user-specific information to the response
        rep["user_info"] = {
            "registration_status": self.get_user_registration_status(instance),
            "is_organizer": self.get_is_user_organizer(instance)
        }
        return rep
        
class SimplifiedAreaLocationSerializer(serializers.ModelSerializer):
    '''
    Simplified AreaLocation serializer for dropdowns, lists, etc
    '''
    unit_name = serializers.CharField(source="unit.unit_name", read_only=True)
    chapter_name = serializers.CharField(source="unit.chapter.chapter_name", read_only=True)
    cluster_id = serializers.CharField(source="unit.chapter.cluster.cluster_id", read_only=True)

    class Meta:
        model = AreaLocation
        fields = [
            "id", 
            "area_name",   
            "unit_name",
            "chapter_name",
            "cluster_id"
        ]
        
class EventSerializer(serializers.ModelSerializer):
    """
    Event serializer for full detail - for event organizers/admins
    """
    
    name = serializers.CharField(required=True)
    event_type = serializers.ChoiceField(choices=Event.EventType.choices, required=True)
    supervising_youth_heads = SimplifiedCommunityUserSerializer(
        read_only=True, many=True
    )
    supervisor_ids = serializers.PrimaryKeyRelatedField(
        source="supervising_youth_heads",
        queryset=get_user_model().objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    
    supervising_CFC_coordinators = SimplifiedCommunityUserSerializer(
        read_only=True, many=True
    )
    cfc_coordinator_ids = serializers.PrimaryKeyRelatedField(
        source="supervising_CFC_coordinators",
        queryset=get_user_model().objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    # Statistics and display fields
    participants_count = serializers.IntegerField(
        source="participants.count", read_only=True
    )
    duration_days = serializers.SerializerMethodField(read_only=True)
    # Location
    areas_involved = SimplifiedAreaLocationSerializer(many=True, read_only=True)
    area_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        help_text="List of area names, e.g. ['Frimley', 'Horsham']"
    )
    
    # Venues
    venues = EventVenueSerializer(many=True, read_only=True)
    venue_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of venue dicts, e.g. [{'venue_name': 'name', 'address': 'address', 'capacity': 100}]"
    )

    # Resources
    resources = PublicEventResourceSerializer(many=True, read_only=True)
    resource_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of resource dicts, e.g. [{'resource_name': 'name', 'description': 'description', 'type': 'type'}]"
    )
    extra_questions = ExtraQuestionSerializer(many=True, read_only=True)
    memo = PublicEventResourceSerializer(read_only=True)
    
    # File upload field for landing image
    landing_image_file = serializers.ImageField(
        write_only=True,
        required=False,
        help_text="Upload a new landing image file"
    )
    
    payment_packages = EventPaymentPackageSerializer(many=True, read_only=True)
    payment_methods = EventPaymentMethodSerializer(many=True, read_only=True)
    
    # Write-only payment fields for updating
    payment_packages_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of payment package dicts for creation/update. Supports 'available_from', 'available_until', and 'deadline' (legacy) fields for date availability."
    )
    payment_methods_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of payment method dicts for creation/update"
    )
    
    organisers = serializers.SerializerMethodField(read_only=True)
    service_team = serializers.SerializerMethodField(read_only=True)
    has_merch = serializers.SerializerMethodField(read_only=True, default=False)

    def to_internal_value(self, data):
        # Handle nested data structures sent from frontend
        
        # Handle basic_info nested structure
        if 'basic_info' in data:
            basic_info = data.pop('basic_info')
            for key, value in basic_info.items():
                data[key] = value
        
        # Handle venue nested structure
        if 'venue' in data:
            venue_data = data.pop('venue')
            for key, value in venue_data.items():
                data[key] = value
        
        # Handle people nested structure
        if 'people' in data:
            people_data = data.pop('people')
            for key, value in people_data.items():
                data[key] = value
        
        # Handle payment data sent from frontend
        if 'payment_packages' in data and isinstance(data['payment_packages'], list):
            data['payment_packages_data'] = data.pop('payment_packages')
        if 'payment_methods' in data and isinstance(data['payment_methods'], list):
            data['payment_methods_data'] = data.pop('payment_methods')
        
        # Handle resource data sent from frontend
        if 'resource_data' in data and isinstance(data['resource_data'], list):
            # Keep the resource_data as is, it's already in the correct format
            pass
        
        return super().to_internal_value(data)

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
            "landing_image_file",
            "is_public",
            "start_date",
            "end_date",
            "duration_days",
            "area_type",
            "number_of_pax",
            "theme",
            "anchor_verse",
            "areas_involved",
            "area_names",
            "area_type",
            "venues",
            "venue_data",
            "resources",
            "resource_data",
            "memo",
            "notes",
            "extra_questions",
            "status",
            "age_range",
            "expected_attendees",
            "maximum_attendees",
            "payment_packages",
            "payment_methods",
            "payment_packages_data",
            "payment_methods_data",
            "organisers",
            "service_team",
            "important_information",
            "what_to_bring",
            "auto_approve_participants",
            # date information
            "registration_deadline",
            "registration_open",
            "registration_open_date",
            "payment_deadline", 
            # Participants / service team
            "participants_count",
            # Write-only supervisor fields
            "supervising_youth_heads",
            "supervisor_ids",
            "supervising_CFC_coordinators",
            "cfc_coordinator_ids",
            "has_merch",
            "format_verifier", 
            "required_existing_id",
            "existing_id_name",
            "existing_id_description"
            ]
        read_only_fields = [
            "id",
            "duration_days",
            "participants_count",
            "youth_head",
            "cfc_coordinator",
            "resources",
            "memo",
            "has_merch",
        ]

    def get_duration_days(self, obj):
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days + 1
        return None
    
    def get_has_merch(self, obj):
        if isinstance(obj, Event):
            return obj.products.exists()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # pprint.pprint(rep)  # ! DEBUG ONLY
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
                "registration_open": rep["registration_open"],
                "status": rep["status"],
                "landing_image": rep["landing_image"],
                "important_information": rep["important_information"],
                "what_to_bring": rep["what_to_bring"],
                "auto_approve_participants": rep["auto_approve_participants"],
            },
            "dates": {
                "start_date": rep["start_date"],
                "end_date": rep["end_date"],
                "duration_days": rep["duration_days"],
                # "registration_open": rep["registration_open"],
                "registration_open_date": rep["registration_open_date"],
                "registration_deadline": rep["registration_deadline"],
                "payment_deadline": rep["payment_deadline"],
            },
            "venue": {
                "venues": rep["venues"],
                "areas_involved": rep["areas_involved"],
                "area_type": rep["area_type"],
            },
            "people": {
                "participants_count": rep["participants_count"],
                "event_heads": rep["supervising_youth_heads"],
                "cfc_coordinators": rep["supervising_CFC_coordinators"],
                "maximum_attendees": rep["maximum_attendees"],
                "expected_attendees": rep["expected_attendees"],
                "age_range": rep["age_range"],
                "organisers": rep["organisers"],
                "service_team": rep["service_team"],
            },
            "resources": {
                "memo": rep["memo"],
                "extra_resources": rep["resources"],
            },
            "notes": rep["notes"],
            "extra_questions": rep["extra_questions"],
            "payment_packages": rep["payment_packages"],
            "payment_methods": rep["payment_methods"],
            "admin": {
                "require_existing_id": rep["required_existing_id"],
                "format_verifier": rep["format_verifier"],
                "existing_id_name": rep["existing_id_name"],
                "existing_id_description": rep["existing_id_description"]
            }
        }

    def get_service_team(self, obj):
        return EventServiceTeamMemberSerializer(
            EventServiceTeamMember.objects.filter(event=obj)
            .select_related('user')
            .prefetch_related('roles'),
            many=True
        ).data

    def get_organisers(self, obj):
        return SimplifiedEventServiceTeamMemberSerializer(
            EventServiceTeamMember.objects.filter(
                Q(roles__role_name=EventRole.EventRoleTypes.EVENT_HEADS) & Q(head_of_role=True) | 
                Q(roles__role_name=EventRole.EventRoleTypes.TEAM_LEADER ) & Q(head_of_role=True) |
                Q(roles__role_name=EventRole.EventRoleTypes.CFC_COORDINATOR ) & Q(head_of_role=True),
                event=obj
            ).distinct(),
            many=True
        ).data

    def validate(self, attrs):
        
        # ensure that name of event is unqiue at anytime
        name = attrs.get('name', None)
        if name:
            existing_event = Event.objects.filter(name=name).exclude(id=self.instance.id if self.instance else None).first()
            if existing_event:
                raise serializers.ValidationError({"name": _("An event with this name already exists. Please choose a different name.")})
        
        return super().validate(attrs)
        
    def create(self, validated_data):
        start_date = validated_data.get('start_date', timezone.now())
        validated_data['start_date'] = start_date
        
        area_names = validated_data.pop('area_names', [])
        venue_data = validated_data.pop('venue_data', [])
        resource_data = validated_data.pop('resource_data', [])
        memo_data = validated_data.pop('memo_data', {})
        supervisor_ids = validated_data.pop('supervisor_ids', [])
        cfc_coordinator_ids = validated_data.pop('cfc_coordinator_ids', [])
        
        # pprint.pprint("Event serializer 'EventSerializer.create' validated data", validated_data)
        
        with transaction.atomic():

            self.validate(validated_data)
            event = Event.objects.create(**validated_data)
            
            area_names = [area.lower() for area in area_names]
            # Areas
            if area_names:
                for area in area_names:
                    if not AreaLocation.objects.filter(area_name=area.lower()).exists():
                        raise serializers.ValidationError({"area_names": _(f"Area '{area}' does not exist.")})
    
                areas = get_list_or_404(AreaLocation, area_name__in=area_names)
                event.areas_involved.set(areas)

            # Venue
            if venue_data:
                venue_serializer = EventVenueSerializer(data=venue_data, many=True)
                venue_serializer.is_valid(raise_exception=True)
                venues = venue_serializer.save()
                event.venues.set(venues)

            # Supervisors
            if supervisor_ids:
                event.supervising_youth_heads.set(supervisor_ids)
            if cfc_coordinator_ids:
                event.supervising_CFC_coordinators.set(cfc_coordinator_ids)

            # Resources
            if resource_data:
                for resource_item in resource_data:
                    # Prepare resource data
                    mapped_data = {
                        'resource_name': resource_item.get('resource_name', ''),
                        'resource_link': resource_item.get('resource_link', ''),
                        'public_resource': resource_item.get('public_resource', False),
                        'added_by': self.context['request'].user.id if 'request' in self.context else None,
                    }
                    
                    # Handle file uploads
                    if 'image_file' in resource_item:
                        mapped_data['image'] = resource_item['image_file']
                    elif 'resource_file' in resource_item:
                        mapped_data['resource_file'] = resource_item['resource_file']
                    
                    resource_serializer = PublicEventResourceSerializer(data=mapped_data)
                    resource_serializer.is_valid(raise_exception=True)
                    resource = resource_serializer.save()
                    event.resources.add(resource)

            # Memo
            if memo_data:
                memo_serializer = PublicEventResourceSerializer(data=memo_data)
                memo_serializer.is_valid(raise_exception=True)
                memo = memo_serializer.save()
                event.memo = memo

            event.save()
        return event
    
    def update(self, instance, validated_data):
        """
        Update an existing Event instance with comprehensive data handling.
        
        This method handles complex nested updates including venues, resources, areas,
        supervisors, payment packages, and payment methods. It supports both frontend
        nested structures and flat data formats.
        
        Example API request payload:
        {
            "basic_info": {
                "name": "Updated Youth Conference 2025",
                "event_type": "conference",
                "description": "An amazing updated youth conference for spiritual growth",
                "sentence_description": "Join us for an incredible spiritual journey",
                "theme": "Walking in Faith",
                "anchor_verse": "Hebrews 11:1",
                "is_public": true,
                "status": "published",
                "auto_approve_participants": false,
                "important_information": "Bring your Bible and notebook",
                "what_to_bring": "Bible, notebook, water bottle"
            },
            "dates": {
                "start_date": "2025-07-15T09:00:00Z",
                "end_date": "2025-07-17T18:00:00Z",
                "registration_open_date": "2025-06-01T00:00:00Z",
                "registration_deadline": "2025-07-10T23:59:59Z",
                "payment_deadline": "2025-07-12T23:59:59Z"
            },
            "venue": {
                "area_names": ["london", "birmingham"],
                "venue_data": [
                    {
                        "id": "existing-venue-uuid",  // Include ID to update existing
                        "venue_name": "Updated Main Hall",
                        "address": "123 Updated Street, London",
                        "capacity": 500,
                        "primary_venue": true
                    },
                    {
                        // No ID = new venue
                        "venue_name": "New Breakout Room",
                        "address": "456 New Avenue, London", 
                        "capacity": 50,
                        "primary_venue": false
                    }
                ]
            },
            "people": {
                "supervisor_ids": ["uuid1", "uuid2"],  // Youth head IDs
                "cfc_coordinator_ids": ["uuid3", "uuid4"],  // CFC coordinator IDs
                "maximum_attendees": 400,
                "expected_attendees": 350,
                "age_range": "16-25"
            },
            "resource_data": [
                {
                    "id": "existing-resource-uuid",  // Include ID to update existing
                    "resource_name": "Updated Conference Handbook",
                    "resource_link": "https://example.com/updated-handbook.pdf",
                    "public_resource": true
                },
                {
                    // No ID = new resource
                    "resource_name": "Prayer Guide",
                    "resource_link": "https://example.com/prayer-guide.pdf",
                    "public_resource": false,
                    "image_file": "<file_object>",  // Optional file upload
                    "resource_file": "<file_object>"  // Alternative file upload
                }
            ],
            "payment_packages": [
                {
                    "name": "Early Bird Special",
                    "description": "Special pricing for early registrations",
                    "price": "25.00",  // String format for £25.00
                    "currency": "GBP",
                    "capacity": 100,
                    "available_from": "2025-05-01T00:00:00",  // ISO format or HTML datetime-local
                    "available_until": "2025-06-30T23:59:59",  // ISO format or HTML datetime-local
                    "deadline": "2025-06-30T23:59:59",  // Legacy support - maps to available_until
                    "is_active": true
                },
                {
                    "name": "Standard Registration",
                    "description": "Regular conference registration",
                    "price": "35.00",
                    "currency": "GBP",
                    "capacity": 300,
                    "available_from": "2025-07-01T00:00:00",
                    "is_active": true
                }
            ],
            "payment_methods": [
                {
                    "id": "existing-method-uuid",  // Include ID to update existing
                    "method_type": "bank-transfer",
                    "instructions": "Transfer to the account below",
                    "account_name": "Youth Conference Fund",
                    "account_number": "12345678",
                    "sort_code": "12-34-56",
                    "reference_instruction": "Use your name as reference",
                    "reference_example": "JohnSmith-YC2025",
                    "important_information": "Allow 3-5 working days",
                    "percentage_fee_add_on": 0,
                    "is_active": true
                },
                {
                    // No ID = new method
                    "method_type": "stripe",
                    "instructions": "Pay securely online with card",
                    "percentage_fee_add_on": 2.5,
                    "is_active": true
                }
            ],
            "landing_image_file": "<file_object>",  // Optional new image upload
            "notes": "Updated event notes for organizers"
        }
        
        Alternative flat format (legacy support):
        {
            "name": "Updated Conference Name",
            "start_date": "2025-07-15T09:00:00Z", 
            "area_names": ["london", "birmingham"],
            "venue_data": [...],
            "resource_data": [...],
            "payment_packages_data": [...],  // Alternative field name
            "payment_methods_data": [...]    // Alternative field name
        }
        """
        # similar to create, but update existing instance
        # start_date = validated_data.get('start_date', timezone.now())
        # validated_data['start_date'] = start_date
        
        area_names = validated_data.pop('area_names', [])
        venue_data = validated_data.pop('venue_data', [])
        resource_data = validated_data.pop('resource_data', [])
        memo_data = validated_data.pop('memo_data', {})
        supervisor_ids = validated_data.pop('supervisor_ids', [])
        supervising_adults = validated_data.pop("supervising_CFC_coordinators", [])
        supervising_youth = validated_data.pop("supervising_youth_heads", [])
        cfc_coordinator_ids = validated_data.pop('cfc_coordinator_ids', [])
        landing_image_file = validated_data.pop('landing_image_file', None)
        
        # Payment-related data - accept both field names for compatibility
        payment_packages_data = validated_data.pop('payment_packages_data', None) or validated_data.pop('payment_packages', None)
        payment_methods_data = validated_data.pop('payment_methods_data', None) or validated_data.pop('payment_methods', None)

        with transaction.atomic():
            self.validate(validated_data)
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            # Handle landing image file upload
            if landing_image_file:
                instance.landing_image = landing_image_file
            # Areas
            if area_names:
                area_names = [area.lower().strip() for area in area_names]
                for area in area_names:
                    if not AreaLocation.objects.filter(area_name=area.lower()).exists():
                        raise serializers.ValidationError({"area_names": _(f"Area '{area}' does not exist.")})

                areas = get_list_or_404(AreaLocation, area_name__in=area_names)
                instance.areas_involved.set(areas)

            # Venue - Handle CRUD operations
            if venue_data is not None and len(venue_data) > 0:
                # Keep track of existing venues
                print("venue data : ", venue_data)
                existing_venues = {venue.id: venue for venue in instance.venues.all()}
                processed_ids = set()
                
                for venue_item in venue_data:
                    venue_id = venue_item.get('id')
                    
                    if venue_id and venue_id in existing_venues:
                        # Update existing venue
                        venue_serializer = EventVenueSerializer(
                            existing_venues[venue_id], 
                            data=venue_item, 
                            partial=True
                        )
                        if venue_serializer.is_valid(raise_exception=True):
                            venue_serializer.save()
                            processed_ids.add(venue_id)
                    else:
                        # Create new venue
                        venue_serializer = EventVenueSerializer(data=venue_item)
                        if venue_serializer.is_valid(raise_exception=True):
                            venue = venue_serializer.save()
                            instance.venues.add(venue)
                            processed_ids.add(venue.id)
                
                # Remove venues that weren't in the update
                for venue_id, venue in existing_venues.items():
                    if venue_id not in processed_ids:
                        instance.venues.remove(venue)
                        venue.delete()

            # Supervisors
            if supervising_youth:
                instance.supervising_youth_heads.set(supervising_youth)
            if supervising_adults:
                instance.supervising_CFC_coordinators.set(supervising_adults)

            # Resources - Handle CRUD operations
            if resource_data is not None:
                # Keep track of existing and new resource IDs
                existing_resources = {resource.id: resource for resource in instance.resources.all()}
                processed_ids = set()
                
                for resource_item in resource_data:
                    # Prepare resource data
                    mapped_data = {
                        'resource_name': resource_item.get('resource_name', ''),
                        'resource_link': resource_item.get('resource_link', ''),
                        'public_resource': resource_item.get('public_resource', False),
                        'added_by': self.context['request'].user.id if 'request' in self.context else None,
                    }
                    
                    # Handle file uploads
                    if 'image_file' in resource_item:
                        mapped_data['image'] = resource_item['image_file']
                    elif 'resource_file' in resource_item:
                        mapped_data['resource_file'] = resource_item['resource_file']
                    
                    resource_id = resource_item.get('id')
                    if resource_id and resource_id in existing_resources:
                        # Update existing resource
                        resource_serializer = PublicEventResourceSerializer(
                            existing_resources[resource_id], 
                            data=mapped_data, 
                            partial=True
                        )
                        resource_serializer.is_valid(raise_exception=True)
                        resource_serializer.save()
                        processed_ids.add(resource_id)
                    else:
                        # Create new resource
                        resource_serializer = PublicEventResourceSerializer(data=mapped_data)
                        resource_serializer.is_valid(raise_exception=True)
                        new_resource = resource_serializer.save()
                        instance.resources.add(new_resource)
                        processed_ids.add(new_resource.id)
                
                # Remove resources that weren't in the update
                # But don't delete resources that are referenced by the memo field
                for resource_id, resource in existing_resources.items():
                    if resource_id not in processed_ids:
                        instance.resources.remove(resource)
                        # Only delete the resource if it's not referenced by the memo field
                        if instance.memo != resource:
                            resource.delete()

            # Memo
            if memo_data:
                memo_serializer = PublicEventResourceSerializer(data=memo_data)
                memo_serializer.is_valid(raise_exception=True)
                memo = memo_serializer.save()
                instance.memo = memo

            # Payment Packages - Replace existing with new ones
            if payment_packages_data is not None:
                # Clear existing packages
                instance.payment_packages.all().delete()
                
                # Create new packages
                from .payment_serializers import EventPaymentPackageSerializer
                from django.utils.dateparse import parse_datetime
                
                for package_data in payment_packages_data:
                    # Map frontend field names to model field names
                    mapped_data = {
                        'event': instance.id,
                        'name': package_data.get('name', ''),
                        'description': package_data.get('description', ''),
                        'price': float(package_data.get('price', 0)),  # Price already in pounds
                        'currency': package_data.get('currency', 'GBP').lower(),
                        'capacity': package_data.get('capacity'),
                        'is_active': package_data.get('is_active', True),
                    }
                    
                    # Handle datetime conversion for available_from
                    available_from = package_data.get('available_from')
                    if available_from and available_from.strip():
                        try:                            
                            # Handle HTML datetime-local format (YYYY-MM-DDTHH:MM)
                            if isinstance(available_from, str):
                                available_from = available_from.strip()
                                
                                # Add seconds if missing (HTML datetime-local format)
                                if 'T' in available_from and len(available_from) == 16:
                                    available_from += ':00'
                                
                                # Parse the datetime
                                parsed_datetime = parse_datetime(available_from)
                                if parsed_datetime:
                                    # Make timezone aware if naive
                                    if timezone.is_naive(parsed_datetime):
                                        parsed_datetime = timezone.make_aware(parsed_datetime)
                                    mapped_data['available_from'] = parsed_datetime
                                    
                        except (ValueError, TypeError) as e:
                            # Log the error for debugging
                            print(f"Error parsing available_from '{available_from}': {e}")
                            # Skip invalid datetime - don't set the field
                    
                    # Handle datetime conversion for available_until (deadline for backward compatibility)
                    available_until = package_data.get('available_until') or package_data.get('deadline')
                    if available_until and available_until.strip():
                        try:                            
                            # Handle HTML datetime-local format (YYYY-MM-DDTHH:MM)
                            if isinstance(available_until, str):
                                available_until = available_until.strip()
                                
                                # Add seconds if missing (HTML datetime-local format)
                                if 'T' in available_until and len(available_until) == 16:
                                    available_until += ':00'
                                
                                # Parse the datetime
                                parsed_datetime = parse_datetime(available_until)
                                if parsed_datetime:
                                    # Make timezone aware if naive
                                    if timezone.is_naive(parsed_datetime):
                                        parsed_datetime = timezone.make_aware(parsed_datetime)
                                    mapped_data['available_until'] = parsed_datetime
                                    
                        except (ValueError, TypeError) as e:
                            # Log the error for debugging
                            print(f"Error parsing available_until '{available_until}': {e}")
                            # Skip invalid datetime - don't set the field
                    
                    package_serializer = EventPaymentPackageSerializer(data=mapped_data)
                    package_serializer.is_valid(raise_exception=True)
                    package_serializer.save()

            # Payment Methods - Replace existing with new ones
            if payment_methods_data is not None:
                from .payment_serializers import EventPaymentMethodSerializer
                
                # Keep track of existing and new method IDs
                existing_methods = {method.id: method for method in instance.payment_methods.all()}
                processed_ids = set()
                
                for method_data in payment_methods_data:
                    # Map frontend field names to model field names
                    method_type = method_data.get('method_type', 'other')
                    
                    # Map frontend method types to model choices
                    method_mapping = {
                        'stripe': 'STRIPE',
                        'bank-transfer': 'BANK',
                        'cash': 'CASH',
                        'paypal': 'PAYPAL',
                        'other': 'OTHER',
                    }
                    
                    mapped_data = {
                        'event': instance.id,
                        'method': method_mapping.get(method_type.lower(), 'OTHER'),
                        'instructions': method_data.get('instructions', ''),
                        'account_name': method_data.get('account_name', ''),
                        'account_number': method_data.get('account_number', ''),
                        'sort_code': method_data.get('sort_code', ''),
                        'reference_instruction': method_data.get('reference_instruction', ''),
                        'reference_example': method_data.get('reference_example', ''),
                        'important_information': method_data.get('important_information', ''),
                        'percentage_fee_add_on': method_data.get('percentage_fee_add_on', 0),
                        'is_active': method_data.get('is_active', True),
                    }
                    
                    method_id = method_data.get('id')
                    if method_id and method_id in existing_methods:
                        # Update existing method
                        method_serializer = EventPaymentMethodSerializer(
                            existing_methods[method_id], 
                            data=mapped_data, 
                            partial=True
                        )
                        method_serializer.is_valid(raise_exception=True)
                        method_serializer.save()
                        processed_ids.add(method_id)
                    else:
                        # Create new method
                        method_serializer = EventPaymentMethodSerializer(data=mapped_data)
                        method_serializer.is_valid(raise_exception=True)
                        new_method = method_serializer.save()
                        processed_ids.add(new_method.id)
                
                # Delete methods that weren't in the update
                for method_id, method in existing_methods.items():
                    if method_id not in processed_ids:
                        method.delete()

            instance.save()
        return instance


class EventParticipantSerializer(serializers.ModelSerializer):
    '''
    Full detail Event participant serializer - for event organizers/admins
    '''
    event = serializers.CharField(source="event.event_code")
    user_details = SimplifiedCommunityUserSerializer(source="user", required=False)
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
    allergies = SimpleAllergySerializer(
        source="user.user_allergies", many=True, required=False
    )
    emergency_contacts = SimpleEmergencyContactSerializer(
        source="user.community_user_emergency_contacts", many=True, required=False
    )
    medical_conditions = SimpleMedicalConditionSerializer(
        source="user.user_medical_conditions", many=True, required=False
    )
    payment_date = serializers.DateTimeField(read_only=True)
    participant_event_payments = EventPaymentSerializer(many=True, read_only=True)
    event_question_answers = QuestionAnswerSerializer(many=True)
    
    # write only fields
    payment_method = serializers.PrimaryKeyRelatedField(
        source="payment_methods",
        queryset=EventPaymentMethod.objects.all(),
        write_only=True,
        required=False,
    )
    payment_package = serializers.PrimaryKeyRelatedField(
        source="payment_packages",
        queryset=EventPaymentPackage.objects.all(),
        write_only=True,
        required=False,
    )
    consent = serializers.DictField(
        write_only=True,    
        required=False,
        help_text="Dictionary containing consent fields, e.g. 'consent: {photos: false, dataProtection: false, terms: false,newsletter: false}'"
    )
    carts_display = serializers.SerializerMethodField()

    class Meta:
        model = EventParticipant
        fields = [
            # identity
            "id",
            "event",
            "user_details",
            "event_pax_id",
            # status
            "status",
            "status_display",
            "participant_type",
            "participant_type_display",
            "registered_on",
            "confirmed_on",
            "attended_on",
            # consents
            "media_consent",
            "data_consent",
            "understood_registration",
            "terms_and_conditions_consent",
            "news_letter_consent",
            # health and emergency
            "allergies",
            "emergency_contacts",
            "medical_conditions",
            "accessibility_requirements",
            "special_requests",
            # metadata
            "notes",
            "paid_amount",
            "payment_date",
            "verified",
            "event_question_answers",
            "participant_event_payments",
            "payment_method",
            "payment_package",
            "consent",
            "carts_display"
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
        
    def get_carts_display(self, obj):
        user = obj.user
        carts = shop_models.EventCart.objects.filter(user=user, event=obj.event)
        serializer = shop_serializers.EventCartSerializer(carts, many=True)
        return serializer.data
        

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {
            "event": rep["event"],
            "event_user_id": rep["event_pax_id"],
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
                "allergies": rep["allergies"],
                "medical_conditions": rep["medical_conditions"],
            },
            "emergency_contacts": rep["emergency_contacts"],
            "notes": rep["notes"],
            "payment": {
                "paid_amount": rep["paid_amount"],
            },
            "verified": rep["verified"],
            "event_payments": rep["participant_event_payments"],
            "carts": rep["carts_display"],
            "questions_answered": rep["event_question_answers"],
        }
                
    def create(self, validated_data):
        '''
        Create or update a participant's registration for an event. Also can provide extra user information 
        via this serializer to update their user profile with medical conditions, emergency contacts, allergies, etc.
        '''        
        # User must be logged in to register for an event
        user = self.context['request'].user
        if not user.is_authenticated:
            raise serializers.ValidationError({"user": _("Authentication required to register for an event.")})
        user_data = validated_data.pop('user', {})
        allergies_data = user_data.pop('user_allergies', [])
        emergency_contacts_data = user_data.pop('community_user_emergency_contacts', [])
        medical_conditions_data = user_data.pop('user_medical_conditions', [])
        question_answers_data = validated_data.pop('event_question_answers', [])

        pprint.pprint(user_data)
        
        event_data = validated_data.pop('event', None)
        event_code = event_data.get('event_code') if event_data else None
        event = Event.objects.filter(Q(event_code = event_code) | Q(id = event_code)).first()
        if EventParticipant.objects.filter(event=event, user=user).exists():
            raise serializers.ValidationError({"non_field_errors": _("You are already registered for this event.")})  
        if not event:
            raise serializers.ValidationError({"event": _("Event with this code does not exist. %s" % event_code)})

        changes = {
            "user_updates": [],
            "medical_conditions_added": [],
            "medical_conditions_linked": [],
            "emergency_contacts_added": [],
            "emergency_contacts_linked": [],
            "allergies_added": [],
            "allergies_linked": [],
            "questions_answered": [],
        }
        
        # pprint.pprint(question_answers_data)

        # uses full version serialiser, take user informatin and update the user record if they want to override their existing data
        with transaction.atomic():
            area = user_data.pop("area", None)
            user_serializer = SimplifiedCommunityUserSerializer(user, data=user_data, partial=True) # used for restrictive updates
            user_serializer.is_valid(raise_exception=True)
            updated_user = user_serializer.save()
            if area:
                area = get_object_or_404(AreaLocation, area_name=area)
                updated_user.area_from = area
                updated_user.save()

            # Track user field changes
            for field, value in user_data.items():
                old_value = getattr(user, field, None)
                if old_value != value:
                    changes["user_updates"].append(f"{field}: '{old_value}' -> '{value}'")

            # Medical conditions
            for medical_condition in medical_conditions_data:
                condition = medical_condition.get('condition', {})
                condition_name = condition.get('name') if condition else None
                condition_model = MedicalCondition.objects.filter(name__iexact=condition_name).first()
                if condition_model and not updated_user.user_medical_conditions.filter(id=condition_model.id).exists():
                    updated_user.medical_conditions.add(condition_model)
                    changes["medical_conditions_linked"].append(condition_name)
                elif condition_name and not updated_user.user_medical_conditions.filter(condition__name__iexact=condition_name).exists():
                    condition["user"] = updated_user.id  # associate new condition with user
                    new_condition = SimpleMedicalConditionSerializer(data=condition)
                    if new_condition.is_valid(raise_exception=True):
                        new_condition.save()
                        updated_user.user_medical_conditions.add(new_condition.instance)
                        changes["medical_conditions_added"].append(condition_name)
                else:
                    raise serializers.ValidationError({"medical_conditions": _("Medical condition name is required.")})
            # Emergency contacts
            for contact in emergency_contacts_data:
                first_name = contact.get('first_name')
                last_name = contact.get('last_name')
                phone_number = contact.get('phone_number')
                if (first_name and last_name) or phone_number:
                    existing_contact = EmergencyContact.objects.filter(
                        Q(
                            (Q(first_name__iexact=first_name) & Q(last_name__iexact=last_name)) |
                            Q(phone_number=phone_number)
                        ),
                        user=updated_user
                    ).first()
                    if not existing_contact:
                        contact["user"] = updated_user.id  
                        new_contact = SimpleEmergencyContactSerializer(data=contact)
                        if new_contact.is_valid(raise_exception=True):
                            new_contact.save()
                            updated_user.community_user_emergency_contacts.add(new_contact.instance)
                            changes["emergency_contacts_added"].append(f"{first_name} {last_name or ''}".strip())
                    else:
                        changes["emergency_contacts_linked"].append(f"{first_name} {last_name or ''}".strip())
                else:
                    raise serializers.ValidationError({"emergency_contacts": _("First name, last name, and phone number are required for emergency contacts.")})

            # Allergies
            for allergy in allergies_data:
                allergy_info = allergy.get('allergy', {})
                allergy_name = allergy_info.get('name') if allergy_info else None
                allergy_model = Allergy.objects.filter(name__iexact=allergy_name).first()
                if allergy_model and not updated_user.user_allergies.filter(id=allergy_model.id).exists():
                    updated_user.allergies.add(allergy_model)
                    changes["allergies_linked"].append(allergy_name)
                elif allergy_name and not updated_user.user_allergies.filter(allergy__name__iexact=allergy_name).exists():
                    allergy_info["user"] = updated_user.id
                    new_allergy = SimpleAllergySerializer(data=allergy_info)
                    if new_allergy.is_valid(raise_exception=True):
                        new_allergy.save()
                        updated_user.user_allergies.add(new_allergy.instance)
                        changes["allergies_added"].append(allergy_name)
                        
            payment_method: EventPaymentMethod = validated_data.pop('payment_methods', None)
            payment_package: EventPaymentPackage = validated_data.pop('payment_packages', None)
            
            event_pax_id = validated_data.pop("event_pax_id", None) # by default not allowed to be overriden so use as a secondary
            
            if not event.required_existing_id and event_pax_id:
                raise serializers.ValidationError("event_pax_id cannot be provided for an event that requires a secondary ID")
            
            validated_data["secondary_reference_id"] = event_pax_id
            
            participant = EventParticipant.objects.create(event=event, user=updated_user, **validated_data)

            # payment - register the type of payment used
            if payment_package:
                payment_package.save()
                
                if payment_method:
                    status = (
                        EventPayment.PaymentStatus.PENDING if payment_method.method == EventPaymentMethod.MethodType.BANK_TRANSFER 
                        else EventPayment.PaymentStatus.SUCCEEDED
                    )
                    # if bank transfer, then we do not mark as paid until admin verifies payment
                else:
                    status = EventPayment.PaymentStatus.SUCCEEDED if payment_package.price == 0 else EventPayment.PaymentStatus.PENDING
                    # no need for payment method if the package is free, so we mark as paid if the package is free                    
                EventPayment.objects.create(
                    user=participant,
                    event=event,
                    package=payment_package,
                    method=payment_method,
                    amount=payment_package.price if payment_package else 0,
                    currency=payment_package.currency if payment_package else "gbp",
                    status=status
                )
                
                
            else:
                raise serializers.ValidationError({"payment_package": _("Payment package is required.")})
            
                
            # consent data
            consent_data = validated_data.pop('consent', {})
            
            # pprint.pprint("consent_data: " + str(consent_data))
            if consent_data:
                media_consent = consent_data.get('photos', None)
                if media_consent is not None and isinstance(media_consent, bool):
                    validated_data['media_consent'] = media_consent
                data_protection_consent = consent_data.get('dataProtection', None)
                if data_protection_consent is not None and isinstance(data_protection_consent, bool):
                    validated_data['data_consent'] = data_protection_consent
                terms_and_conditions_consent = consent_data.get('terms', None)
                if terms_and_conditions_consent is not None and isinstance(terms_and_conditions_consent, bool):
                    validated_data['terms_and_conditions_consent'] = terms_and_conditions_consent
                newsletter_consent = consent_data.get('newsletter', None)
                if newsletter_consent is not None and isinstance(newsletter_consent, bool):
                    validated_data['news_letter_consent'] = newsletter_consent
                understood_registration = consent_data.get('understood_registration', None)
                if understood_registration is not None and isinstance(understood_registration, bool):
                    validated_data['understood_registration'] = understood_registration

            # for answer in question_answers_data:
            for answer in question_answers_data:
                question = answer.get('question', None)
                if not question:
                    raise serializers.ValidationError({"event_question_answers": _("Each answer must be associated with a question.")})
                answer_text = answer.get('answer_text', '').strip()
                
                selected_choices = answer.get('selected_choices', [])
                answer = QuestionAnswer(participant=participant, question=question, answer_text=answer_text)
                answer.selected_choices.set(selected_choices)
                answer.save()
                changes["questions_answered"].append(f"Question ID {getattr(question, 'question_name', 'No-id')} answered. with answer: {answer_text} and choices: {selected_choices}")
                participant.event_question_answers.add(answer) 
                
            

            pprint.pprint(changes)
        return participant

    #? A little note for the update method, most likely users will need to submit change requests to admins so they can verifiy changes manually    

class SimplifiedEventParticipantSerializer(serializers.ModelSerializer):
    """
    Restrictive serializer for listing participants with minimal information
    """
    event = serializers.CharField(source="event.event_code", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.EmailField(source="user.primary_email", read_only=True)
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




class ParticipantManagementSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for participant management views.
    Eliminates bloated product catalog data while keeping essential participant info.
    
    This serializer reduces response size by 70-80% compared to EventParticipantSerializer
    by removing redundant product details, full cart structures, and unnecessary metadata.
    """
    # User info
    user = serializers.SerializerMethodField()
    
    # Status info
    status = serializers.SerializerMethodField()
    
    # Dates
    dates = serializers.SerializerMethodField()
    
    # Consents
    consents = serializers.SerializerMethodField()
    
    # Health summary (simplified)
    health = serializers.SerializerMethodField()
    
    # Emergency contacts (simplified)
    emergency_contacts = serializers.SerializerMethodField()
    
    # Payment summary (no detailed transaction history)
    payment = serializers.SerializerMethodField()
    
    # Event payments (simplified - no full transaction details)
    event_payments = serializers.SerializerMethodField()
    
    # Carts (simplified - no full product catalog)
    carts = serializers.SerializerMethodField()
    
    # Questions answered (simplified)
    questions_answered = serializers.SerializerMethodField()
    
    # Check-in status (to match WebSocket data)
    checked_in = serializers.SerializerMethodField()
    check_status = serializers.SerializerMethodField()
    check_in_time = serializers.SerializerMethodField()
    check_out_time = serializers.SerializerMethodField()
    attendance_records = serializers.SerializerMethodField()
    
    # Product orders (to match WebSocket data)
    product_orders = serializers.SerializerMethodField()
    questions_asked = serializers.SerializerMethodField()

    class Meta:
        model = EventParticipant
        fields = [
            "event",
            # "event_user_id", 
            "user",
            "status",
            "dates",
            "consents",
            "health",
            "emergency_contacts",
            "notes",
            "payment",
            "verified",
            "event_payments",
            "carts",
            "questions_answered",
            "checked_in",
            "check_status", 
            "check_in_time",
            "check_out_time",
            "attendance_records",
            "product_orders",
            "questions_asked"
        ]
        read_only_fields = fields

    def get_event(self, obj):
        return obj.event.event_code

    def get_event_user_id(self, obj):
        return obj.event_pax_id

    def get_user(self, obj):
        """Essential user info only"""
        # Safely get profile picture URL
        profile_picture_url = None
        try:
            if hasattr(obj.user, 'profile_picture') and obj.user.profile_picture:
                profile_picture_url = obj.user.profile_picture.url
        except (AttributeError, ValueError):
            profile_picture_url = None
        return {
            "first_name": obj.user.first_name,
            "last_name": obj.user.last_name,
            "ministry": getattr(obj.user, 'ministry', None),
            "gender": getattr(obj.user, 'gender', None),
            "date_of_birth": getattr(obj.user, 'date_of_birth', None),
            "member_id": getattr(obj.user, 'member_id', None),
            "username": obj.user.username,
            "profile_picture": profile_picture_url,
            "area_from_display": self._get_area_display(obj.user),
            "primary_email": obj.user.primary_email,
            "phone": obj.user.phone_number,
        }

    def get_status(self, obj):
        return {
            "code": obj.status,
            "participant_type": obj.participant_type,
        }

    def get_dates(self, obj):
        return {
            "registered_on": obj.registration_date,
            "confirmed_on": obj.confirmation_date,
            "attended_on": obj.attended_date,
            "payment_date": obj.payment_date,
        }

    def get_consents(self, obj):
        return {
            "media_consent": obj.media_consent,
            "data_consent": obj.data_consent,
            "understood_registration": obj.understood_registration,
        }

    def get_health(self, obj):
        """Simplified health info - no full medical model details"""
        allergies = []
        medical_conditions = []
        
        for allergy in obj.user.user_allergies.all():
            allergies.append({
                "id": str(allergy.id),
                "name": allergy.allergy.name,
                "severity": allergy.severity,
                "severity_display": allergy.get_severity_display(),
                "instructions": allergy.instructions,
                "notes": allergy.notes,
            })
        
        for condition in obj.user.user_medical_conditions.all():
            medical_conditions.append({
                "id": str(condition.id),
                "name": condition.condition.name,
                "severity": condition.severity,
                "severity_display": condition.get_severity_display(),
                "instructions": condition.instructions,
                "date_diagnosed": condition.date_diagnosed,
            })
        
        return {
            "allergies": allergies,
            "medical_conditions": medical_conditions,
        }

    def get_emergency_contacts(self, obj):
        """Simplified emergency contacts - essential info only"""
        contacts = []
        for contact in obj.user.community_user_emergency_contacts.all():
            contacts.append({
                "id": str(contact.id),
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "phone_number": contact.phone_number,
                "contact_relationship": contact.contact_relationship,
                "contact_relationship_display": contact.get_contact_relationship_display(),
                "is_primary": contact.is_primary,
            })
        return contacts

    def get_payment(self, obj):
        """Payment summary only - no detailed transaction history"""
        return {
            "paid_amount": str(obj.paid_amount),
        }

    def get_event_payments(self, obj):
        """Simplified event payments - no full transaction details"""
        payments = []
        for payment in obj.participant_event_payments.all():
            # Safely get user reference
            user_id = None
            try:
                if hasattr(payment, 'user') and payment.user:
                    user_id = str(payment.user.id)
                elif hasattr(payment, 'participant') and payment.participant and payment.participant.user:
                    user_id = str(payment.participant.user.id)
            except (AttributeError, ValueError):
                user_id = None
                
            # Safely get method display
            method_display = None
            try:
                if hasattr(payment, 'method') and payment.method:
                    method_display = payment.method.get_method_display() if hasattr(payment.method, 'get_method_display') else str(payment.method)
            except (AttributeError, ValueError):
                method_display = None
            
            # Safely format amount
            amount_display = str(payment.amount)
            try:
                if payment.currency and payment.amount:
                    amount_display = f"{float(payment.amount):.2f} {payment.currency.upper()}"
            except (AttributeError, ValueError, TypeError):
                amount_display = str(payment.amount)
            
            payments.append({
                "id": payment.id,
                "user": user_id,
                "participant_details": {
                    "participant_id": str(obj.id),
                    "event_pax_id": obj.event_pax_id,
                    "full_name": f"{obj.user.first_name} {obj.user.last_name}".strip(),
                    "email": obj.user.primary_email,
                    "participant_type": obj.participant_type,
                    "status": obj.status,
                    "registration_date": obj.registration_date,
                },
                "participant_user_email": obj.user.primary_email,
                "event": str(obj.event.id),
                "event_name": obj.event.name,
                "package": payment.package.id if payment.package else None,
                "package_name": payment.package.name if payment.package else None,
                "method": payment.method.id if payment.method else None,
                "method_display": method_display,
                "amount": payment.amount,
                "amount_display": amount_display,
                "currency": getattr(payment, 'currency', None),
                "status": payment.status,
                "status_display": payment.get_status_display() if hasattr(payment, 'get_status_display') else payment.status,
                "event_payment_tracking_number": getattr(payment, 'tracking_number', None),
                "paid_at": getattr(payment, 'paid_at', None),
                "verified": getattr(payment, 'verified', False),
                "created_at": payment.created_at if hasattr(payment, 'created_at') else None,
                "updated_at": payment.updated_at if hasattr(payment, 'updated_at') else None,
                "bank_reference": getattr(payment, 'bank_reference', None),
            })
        return payments

    def get_carts(self, obj):
        """Return simplified cart data - just basic cart info without product bloat"""
        from apps.shop.models import EventCart
        
        carts = EventCart.objects.filter(user=obj.user, event=obj.event)
        
        simplified_carts = []
        for cart in carts:
            # Safely get cart totals
            total = 0.0
            shipping_cost = 0.0
            try:
                total = float(cart.total) if cart.total else 0.0
                shipping_cost = float(cart.shipping_cost) if cart.shipping_cost else 0.0
            except (ValueError, TypeError):
                total = 0.0
                shipping_cost = 0.0
            
            # Basic cart info only
            product_payment = shop_models.ProductPayment.objects.filter(cart=cart).first()

            cart_data = {
                "uuid": str(cart.uuid),
                "user": getattr(cart.user, 'member_id', ''),
                "user_email": getattr(cart.user, 'primary_email', ''),
                "event": str(cart.event.id),
                "event_name": getattr(cart.event, 'name', ''),
                "order_reference_id": getattr(cart, 'order_reference_id', ''),
                "total": total,
                "shipping_cost": shipping_cost,
                "created": getattr(cart, 'created', None),
                "updated": getattr(cart, 'updated', None),
                "approved": getattr(cart, 'approved', False),
                "submitted": getattr(cart, 'submitted', False),
                "active": getattr(cart, 'active', True),
                "notes": getattr(cart, 'notes', ''),
                "shipping_address": getattr(cart, 'shipping_address', ''),
                "orders": [],  # Empty - no product details to reduce size
                "bank_reference": getattr(product_payment, 'bank_reference', None)
            }
            
            # Add minimal order info (no full product catalog)
            try:
                for order in cart.orders.all()[:3]:  # Limit to 3 recent orders
                    product = order.product
                    
                    images = product.images.all() if product and hasattr(product, 'images') else []
                    image_url = images[0].image if images else None
                    
                    # Handle size field properly - convert to string to avoid serialization errors
                    size_value = None
                    try:
                        if hasattr(order, 'size') and order.size is not None:
                            size_value = str(order.size)
                    except Exception:
                        size_value = None
                        
                    order_data = {
                        "id": order.id,
                        "quantity": getattr(order, 'quantity', 1),
                        "status": getattr(order, 'status', 'unknown'),
                        "imageUrl": str(image_url.url) if image_url else None,
                        "price": float(getattr(product, 'price', 0.0)) if getattr(product, 'price', None) else 0.0,
                        "bank_reference": getattr(product_payment, 'bank_reference', None),
                        "size": size_value,  # Now guaranteed to be string or None
                    }
                    
                    # Safely get product title
                    try:
                        order_data["product_title"] = order.product.title
                    except AttributeError:
                        order_data["product_title"] = "Unknown Product"
                    
                    # Safely get status display
                    try:
                        order_data["status_display"] = order.get_status_display()
                    except AttributeError:
                        order_data["status_display"] = order_data["status"].title()
                    
                    cart_data["orders"].append(order_data)
            except AttributeError:
                # If orders relationship doesn't exist, keep empty list
                pass
            
            simplified_carts.append(cart_data)
        
        return simplified_carts

    def get_questions_answered(self, obj):
        """Simplified question responses - no extra metadata"""
        answers = []
        for qa in obj.event_question_answers.all():
            # Safely get selected choices
            selected_choices = []
            try:
                selected_choices = [choice.choice_text for choice in qa.selected_choices.all()]
            except AttributeError:
                # Fallback if choice_text doesn't exist, try other common field names
                try:
                    selected_choices = [choice.text for choice in qa.selected_choices.all()]
                except AttributeError:
                    selected_choices = []
            
            # Safely get question text
            question_text = ""
            try:
                question_text = qa.question.question_text
            except AttributeError:
                try:
                    question_text = qa.question.question_body
                except AttributeError:
                    question_text = getattr(qa.question, 'text', '')
            
            answers.append({
                "id": str(qa.id),
                "participant": str(qa.participant.id),
                "question": str(qa.question.id),
                "answer_text": qa.answer_text,
                "question_text": question_text,
                "selected_choices_display": selected_choices,
            })
        return answers

    def _get_area_display(self, user):
        """Helper method to get area display info"""
        try:
            if hasattr(user, 'area_from') and user.area_from:
                area = user.area_from
                cluster_info = None
                chapter_info = None
                if hasattr(area, 'unit') and area.unit:
                    chapter_info = getattr(area.unit.chapter, 'chapter_name', None)
                    cluster_info = getattr(area.unit.chapter.cluster, 'cluster_id', None)                
                return {
                    "area": getattr(area, 'area_name', None),
                    "chapter": chapter_info,
                    "cluster": cluster_info,
                }
            else:
                return {"area": None, "chapter": None, "cluster": None}
        except AttributeError:
            pass
        return None

    def get_checked_in(self, obj):
        """Get current check-in status"""
        from datetime import date
        today = date.today()
        return obj.user.event_attendance.filter(
            event=obj.event,
            day_date=today,
            check_in_time__isnull=False,
            check_out_time__isnull=True
        ).exists()

    def get_check_status(self, obj):
        """Get detailed check status (not-checked-in, checked-in, checked-out)"""
        from datetime import date
        today = date.today()
        
        latest_attendance = obj.user.event_attendance.filter(
            event=obj.event,
            day_date=today
        ).order_by('-check_in_time').first()
        
        if not latest_attendance or not latest_attendance.check_in_time:
            return 'not-checked-in'
        elif latest_attendance.check_out_time:
            return 'checked-out'
        else:
            return 'checked-in'

    def get_check_in_time(self, obj):
        """Get latest check-in time"""
        from datetime import date
        today = date.today()
        
        latest_attendance = obj.user.event_attendance.filter(
            event=obj.event,
            day_date=today,
            check_in_time__isnull=False
        ).order_by('-check_in_time').first()
        
        return latest_attendance.check_in_time.isoformat() if latest_attendance else None

    def get_check_out_time(self, obj):
        """Get latest check-out time"""
        from datetime import date
        today = date.today()
        
        latest_attendance = obj.user.event_attendance.filter(
            event=obj.event,
            day_date=today,
            check_out_time__isnull=False
        ).order_by('-check_out_time').first()
        
        return latest_attendance.check_out_time.isoformat() if latest_attendance else None

    def get_attendance_records(self, obj):
        """Get all attendance records for this participant"""
        records = []
        for attendance in obj.user.event_attendance.filter(event=obj.event).order_by('-day_date', '-check_in_time'):
            records.append({
                'id': str(attendance.id),
                'day_date': attendance.day_date.isoformat() if attendance.day_date else None,
                'check_in_time': attendance.check_in_time.isoformat() if attendance.check_in_time else None,
                'check_out_time': attendance.check_out_time.isoformat() if attendance.check_out_time else None,
                'day_id': attendance.day_id
            })
        return records

    def get_product_orders(self, obj):
        """Get product orders for this participant"""
        from apps.shop.models import EventProductOrder
        
        # Don't use select_related('size') - it causes Django field errors
        # The 'size' is a ForeignKey to ProductSize, but Django has issues with it
        orders = EventProductOrder.objects.filter(
            cart__user=obj.user,
            cart__event=obj.event
        ).select_related('product')
        
        orders_data = []
        for order in orders:
            # Handle ProductSize field properly - it's a ForeignKey to ProductSize model
            size_value = None
            try:
                if hasattr(order, 'size') and order.size is not None:
                    # order.size is a ProductSize instance, get the size choice value
                    size_value = str(order.size.size) if hasattr(order.size, 'size') else str(order.size)
            except Exception:
                # If any error occurs, fallback to None
                size_value = None
            orders_data.append({
                'id': str(order.id),
                'order_reference_id': getattr(order, 'order_reference_id', None),
                'product_name': order.product.title if order.product else None,
                'size': size_value,  # This is now guaranteed to be a string or None
                'quantity': order.quantity,
                'price_at_purchase': float(order.price_at_purchase) if order.price_at_purchase else order.product.price,
                'discount_applied': float(order.discount_applied) if order.discount_applied else 0.0,
                'status': order.status,
                'changeable': getattr(order, 'changeable', True),
                'change_requested': getattr(order, 'change_requested', False),
                'change_reason': getattr(order, 'change_reason', None),
                'added': order.added.isoformat() if order.added else None
            })
        return orders_data

    def get_questions_asked(self, obj):
        return ParticipantQuestionSerializer(obj.participant_questions, many=True).data
    
    def to_representation(self, instance):
        """Override to use custom field getters"""
        return {
            "event": self.get_event(instance),
            "event_user_id": self.get_event_user_id(instance),
            "user": self.get_user(instance),
            "status": self.get_status(instance),
            "dates": self.get_dates(instance),
            "consents": self.get_consents(instance),
            "health": self.get_health(instance),
            "emergency_contacts": self.get_emergency_contacts(instance),
            "notes": instance.notes,
            "payment": self.get_payment(instance),
            "verified": instance.verified,
            "event_payments": self.get_event_payments(instance),
            "carts": self.get_carts(instance),
            "questions_answered": self.get_questions_answered(instance),
            "checked_in": self.get_checked_in(instance),
            "check_status": self.get_check_status(instance),
            "check_in_time": self.get_check_in_time(instance),
            "check_out_time": self.get_check_out_time(instance),
            "attendance_records": self.get_attendance_records(instance),
            "product_orders": self.get_product_orders(instance),
            "questions_asked": self.get_questions_asked(instance)
        }
        
class EventDayAttendanceSerializer(serializers.ModelSerializer): #! used for future reference, not currently implemented
    '''
    Serializer for event day attendance details.
    '''
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
        
class ParticipantQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for participant questions and answers that participants submit to event organizers.
    
    Example API object:
    {
        "participant": "CNF25ANCRD-123456",  // EventParticipant confirmation number OR UUID
        "event": "456e7890-e89b-12d3-a456-426614174001",       // Event UUID
        "question_subject": "Dietary Requirements Change",
        "question": "I need to change my dietary requirements from vegetarian to vegan. Is this possible?",
        "questions_type": "CHANGE_REQUEST",
        "priority": "MEDIUM"
    }
    
    Response includes additional computed fields:
    {
        "id": "789e0123-e89b-12d3-a456-426614174002",
        "participant_details": {
            "event_pax_id": "CNF25ANCRD-123456",
            "participant_name": "John Smith",
            "participant_email": "john@example.com"
        },
        "event_name": "Anchored Conference 2025",
        "status_display": "Pending",
        "questions_type_display": "Change request",
        "priority_display": "Medium",
        "submitted_at": "2025-01-15T14:30:00Z",
        "updated_at": "2025-01-15T14:30:00Z",
        "responded_at": null,
        "answer": null,
        "admin_notes": null
    }
    """
    participant_details = serializers.SerializerMethodField(read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    questions_type_display = serializers.CharField(source="get_questions_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    
    # Custom field to accept either UUID or confirmation number
    participant = serializers.CharField(write_only=True, help_text="EventParticipant UUID or confirmation number (event_pax_id)")
    answered_by = serializers.CharField(source="answered_by.first_name", read_only=True)
    
    class Meta:
        model = ParticipantQuestion
        fields = [
            "id", "participant", "participant_details", "event", "event_name",
            "question_subject", "question", "questions_type", "questions_type_display",
            "priority", "priority_display", "status", "status_display",
            "submitted_at", "updated_at", "responded_at",
            "answer", "admin_notes", "answered_by"
        ]
        read_only_fields = [
            "id", "participant_details", "event_name", "status_display",
            "questions_type_display", "priority_display", "submitted_at", "updated_at"
        ]
    
    def get_participant_details(self, obj):
        """Get participant details including registration info"""
        if obj.participant and obj.participant.user:
            return {
                "event_pax_id": obj.participant.event_pax_id,
                "participant_name": f"{obj.participant.user.first_name} {obj.participant.user.last_name}",
                "participant_email": obj.participant.user.primary_email,
                "participant_type": obj.participant.participant_type,
                "participant_status": obj.participant.status
            }
        return None
    
    def to_representation(self, instance):
        """Include participant UUID in response for reference"""
        rep = super().to_representation(instance)
        if instance.participant:
            rep['participant'] = str(instance.participant.id)  # Return the actual UUID for reference
        return rep
    
    def create(self, validated_data):
        # Handle participant lookup - accept either UUID or confirmation number
        participant_identifier = validated_data.pop('participant', None)
        if participant_identifier:
            try:
                # First try to find by UUID (if it's a valid UUID format)
                participant = EventParticipant.objects.get(id=participant_identifier)
            except (EventParticipant.DoesNotExist, ValueError, ValidationError):
                # If UUID lookup fails, try by confirmation number (event_pax_id)
                try:
                    participant = EventParticipant.objects.get(event_pax_id=participant_identifier)
                except EventParticipant.DoesNotExist:
                    raise serializers.ValidationError({
                        "participant": f"EventParticipant not found with identifier: {participant_identifier}"
                    })
            
            validated_data['participant'] = participant
            
            # Set event from participant if not provided
            if not validated_data.get('event'):
                validated_data['event'] = participant.event
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle status changes and timestamps
        if 'status' in validated_data:
            if validated_data['status'] == ParticipantQuestion.StatusChoices.ANSWERED and not instance.responded_at:
                instance.responded_at = timezone.now()
                
        return super().update(instance, validated_data)


class SimplifiedEventParticipantSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for EventParticipant - minimal data for basic operations
    """
    user_details = SimplifiedCommunityUserSerializer(source="user", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    participant_type_display = serializers.CharField(source="get_participant_type_display", read_only=True)

    class Meta:
        model = EventParticipant
        fields = [
            "id",
            "event_pax_id",
            "user_details", 
            "status",
            "status_display",
            "participant_type",
            "participant_type_display",
            "registration_date",
            "verified"
        ]
        read_only_fields = fields


class ListEventParticipantSerializer(serializers.ModelSerializer):
    """
    Used specifically for participant tables - includes necessary data for management views
    """
    event = serializers.CharField(source="event.event_code", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.EmailField(source="user.primary_email", read_only=True)
    phone = serializers.CharField(source="user.phone_number", read_only=True)
     
    registration_date = serializers.DateTimeField(read_only=True)
    area_from = serializers.SerializerMethodField()
    merch_data = serializers.SerializerMethodField()
    bank_reference = serializers.SerializerMethodField()
    outstanding_orders_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    participant_type_display = serializers.CharField(source="get_participant_type_display", read_only=True)

    class Meta:
        model = EventParticipant
        fields = [
            "id",
            "event_pax_id",
            "event",  # UUID of event
            "user",   # UUID of user
            "first_name",
            "last_name",
            "email",
            "phone",
            "participant_type",
            "participant_type_display",
            "status",
            "status_display",
            "registration_date",
            "area_from",
            "merch_data",
            "bank_reference",
            "outstanding_orders_count",
            "verified"
        ]
        read_only_fields = fields

    def get_merch_data(self, obj):
        try:
            carts = obj.user.carts.filter(event=obj.event)    
            
            merch_data = []
            for cart in carts:
                cart_data = {
                    "cart_id": str(cart.uuid),
                    "total": cart.total,
                }
                reference = shop_models.ProductPayment.objects.filter(cart=cart).first()
                cart_data["bank_reference"] = reference.bank_reference if reference else None
                cart_data["number_of_items"] = cart.products.count()
                merch_data.append(cart_data)
            return merch_data
        except Exception as e:
            print(f"Error getting merch data for participant {obj.id}: {e}")
            return []
    
    def get_bank_reference(self, obj):
        try:
            reference = EventPayment.objects.filter(user=obj, event=obj.event).first()
            return reference.bank_reference if reference else None
        except Exception as e:
            print(f"Error getting bank reference for participant {obj.id}: {e}")
            return None
    
    def get_area_from(self, obj):
        try:
            if obj.user and obj.user.area_from:
                return {
                    "area": obj.user.area_from.area_name,
                    "chapter": obj.user.area_from.unit.chapter.chapter_name if obj.user.area_from.unit and obj.user.area_from.unit.chapter else None,
                    "cluster": obj.user.area_from.unit.chapter.cluster.cluster_id if obj.user.area_from.unit and obj.user.area_from.unit.chapter and obj.user.area_from.unit.chapter.cluster else None,
                }
            return None
        except AttributeError as e:
            print(f"Error getting area_from for participant {obj.id}: {e}")
            return None
    
    def get_outstanding_orders_count(self, obj):
        """
        Calculate the total number of outstanding orders for this participant.
        This includes:
        1. Unapproved product/merch orders (carts that are submitted but not approved)
        2. Outstanding event booking payments (event payments that are not verified or failed)
        """
        try:
            outstanding_count = 0
            
            # Count unapproved merch orders for this event
            unapproved_carts = obj.user.carts.filter(
                event=obj.event,
                submitted=True,
                approved=False,
                active=True
            )
            outstanding_count += unapproved_carts.count()
            
            # Count outstanding event payments (unverified or failed)
            outstanding_event_payments = EventPayment.objects.filter(
                user=obj,
                event=obj.event
            ).filter(
                Q(verified=False) | Q(status=EventPayment.PaymentStatus.FAILED)
            )
            outstanding_count += outstanding_event_payments.count()
            
            return outstanding_count
            
        except Exception as e:
            print(f"Error calculating outstanding orders for participant {obj.id}: {e}")
            return 0


class EventDayAttendanceSerializer(serializers.ModelSerializer):
    """
    Serializer for EventDayAttendance model
    """
    user_details = SimplifiedCommunityUserSerializer(source="user", read_only=True)
    event_code = serializers.CharField(source="event.event_code", read_only=True)
    duration = serializers.SerializerMethodField()

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
            "stale"
        ]
        read_only_fields = ["id", "duration", "event_code", "user_details"]

    def get_duration(self, obj):
        """Calculate duration between check-in and check-out"""
        if obj.check_in_time and obj.check_out_time:
            # Convert time to datetime for calculation
            from datetime import datetime, date
            check_in_dt = datetime.combine(date.today(), obj.check_in_time)
            check_out_dt = datetime.combine(date.today(), obj.check_out_time)
            
            # Handle case where check-out is next day
            if check_out_dt < check_in_dt:
                from datetime import timedelta
                check_out_dt += timedelta(days=1)
            
            duration = check_out_dt - check_in_dt
            return str(duration)
        return None
