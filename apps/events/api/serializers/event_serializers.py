from rest_framework import serializers
from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventResource,
    AreaLocation, EventVenue
)
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import get_list_or_404
from django.db import transaction
from django.db.models import Q

import pprint

from apps.events.models import EventDayAttendance, Event, QuestionAnswer
from apps.users.api.serializers import (
    SimpleEmergencyContactSerializer, SimplifiedCommunityUserSerializer, 
    SimpleAllergySerializer, SimpleMedicalConditionSerializer,
    CommunityUserSerializer
)
from apps.users.models import CommunityUser, MedicalCondition, Allergy, EmergencyContact
from .location_serializers import EventVenueSerializer, AreaLocationSerializer
from .registration_serializers import ExtraQuestionSerializer, QuestionAnswerSerializer, QuestionChoiceSerializer

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
            "areas_involved",
            "main_venue",
        )
        
    def get_main_venue(self, obj):
        primary_venue = obj.venues.filter(primary_venue=True).first()
        if primary_venue:
            return primary_venue.name
        return None
        
    def get_areas_involved(self, obj):
        return [area.area_name for area in obj.areas_involved.all()]
        
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
                "area_type": rep.get("area_type"),
                "areas_involved": rep.get("areas_involved"),
                "main_venue": rep.get("main_venue"),
            }
        }
        
class SimplifiedAreaLocationSerializer(serializers.ModelSerializer):
    '''
    Simplified AreaLocation serializer for dropdowns, lists, etc
    '''
    unit_name = serializers.CharField(source="unit.unit_name", read_only=True)
    cluster_name = serializers.CharField(source="unit.cluster.cluster_name", read_only=True)

    class Meta:
        model = AreaLocation
        fields = [
            "id", 
            "area_name",   
            "unit_name",
            "cluster_name",
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
            "area_names",
            "venues",
            "venue_data",
            "resources",
            "resource_data",
            "memo",
            "notes",
            "extra_questions",
            # Participants / service team
            "participants_count",
            # Write-only supervisor fields
            "supervising_youth_heads",
            "supervisor_ids",
            "supervising_CFC_coordinators",
            "cfc_coordinator_ids",
        ]
        read_only_fields = [
            "id",
            "duration_days",
            "participants_count",
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
        pprint.pprint(rep)  # ! DEBUG ONLY
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
                "event_heads": rep["supervising_youth_heads"],
                "cfc_coordinators": rep["supervising_CFC_coordinators"],
            },
            "resources": {
                "memo": rep["memo"],
                "extra_resources": rep["resources"],
            },
            "notes": rep["notes"],
            "extra_questions": rep["extra_questions"],
        }
    
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
        
        
        with transaction.atomic():
            self.validate(validated_data)
            event = Event.objects.create(**validated_data)
            
            area_names = [area.lower() for area in area_names]

            # Areas
            if area_names:
                print(AreaLocation.objects.filter(area_name__in=area_names).values_list('area_name', flat=True))
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
                resource_serializer = PublicEventResourceSerializer(data=resource_data, many=True)
                resource_serializer.is_valid(raise_exception=True)
                resources = resource_serializer.save()
                event.resources.set(resources)

            # Memo
            if memo_data:
                memo_serializer = PublicEventResourceSerializer(data=memo_data)
                memo_serializer.is_valid(raise_exception=True)
                memo = memo_serializer.save()
                event.memo = memo

            event.save()
        return event
        
class EventParticipantSerializer(serializers.ModelSerializer):
    '''
    Full detail Event participant serializer - for event organizers/admins
    '''
    event = serializers.CharField(source="event.event_code")
    user_details = SimplifiedCommunityUserSerializer(source="user")
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
    event_question_answers = QuestionAnswerSerializer(many=True)

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
            "allergies",
            "special_needs",
            "emergency_contacts",
            "medical_conditions",
            "notes",
            "paid_amount",
            "payment_date",
            "verified",
            "event_question_answers"
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
                "allergies": rep["allergies"],
                "medical_conditions": rep["medical_conditions"],
                "special_needs": rep["special_needs"],
            },
            "emergency_contacts": rep["emergency_contacts"],
            "notes": rep["notes"],
            "payment": {
                "paid_amount": rep["paid_amount"],
            },
            "verified": rep["verified"]
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

        event_data = validated_data.pop('event', None)
        event_code = event_data.get('event_code') if event_data else None
        event = Event.objects.filter(event_code=event_code).first()
        if EventParticipant.objects.filter(event=event, user=user).exists():
            raise serializers.ValidationError({"non_field_errors": _("You are already registered for this event.")})  
        if not event:
            raise serializers.ValidationError({"event": _("Event with this code does not exist.")})

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
        
        pprint.pprint(question_answers_data)

        # uses full version serialiser, take user informatin and update the user record if they want to override their existing data
        with transaction.atomic():
            user_serializer = SimplifiedCommunityUserSerializer(user, data=user_data, partial=True) # used for restrictive updates
            user_serializer.is_valid(raise_exception=True)
            updated_user = user_serializer.save()

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
            
            # for answer in question_answers_data:
            participant = EventParticipant.objects.create(event=event, user=updated_user, **validated_data)
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

            pprint.pprint(changes) # ! DEBUG ONLY
        return participant

    # TODO: update method, but generally use the user serializer to update user information as each guest
    # has their own user account

class SimplifiedEventParticipantSerializer(serializers.ModelSerializer):
    """
    Flat, minimal participant info for table/list views. 
    DO NOT use for detailed views to create or update participants.
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