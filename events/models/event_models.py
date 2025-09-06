from django.db import models
from django.core import validators
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .location_models import AreaLocation, ChapterLocation, CountryLocation
from users.models import Alergies, EmergencyContact

import uuid

class Event(models.Model):
    '''
    Represents various types of events in the YFC Community
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class EventType(models.TextChoices):
        YOUTH_CAMP = "YOUTH_CAMP", _("Youth Camp")
        CONFERENCE = "CONFERENCE", _("Conference")
        RETREAT = "RETREAT", _("Retreat")
        WORKSHOP = "WORKSHOP", _("Workshop")
        TRAINING = "TRAINING", _("Training")
        PFO = "PFO", _("PFO")
        HOUSEHOLD = "HOUSEHOLD", _("Household")
        FELLOWSHIP = "FELLOWSHIP", _("Fellowship")
        OTHER = "OTHER", _("Other")
        
    class EventAreaType(models.TextChoices):
        AREA = "AREA", _("Area")
        UNIT = "UNIT", _("Unit")
        CLUSTER = "CLUSTER", _("Cluster") 
        NATIONAL = "NATIONAL", _("National")
        CONTINENTAL = "CONTINENTAL", _("Continental")
        INTERNATIONAL = "INTERNATIONAL", _("International")   
        
    # Event type and basic information
    event_type = models.CharField(_("event type"), max_length=20, choices=EventType.choices, default=EventType.YOUTH_CAMP)
    event_description = models.TextField(verbose_name=_("event description"), blank=True, null=True)
    name = models.CharField(_("event name"), max_length=200, blank=True, null=True)  
    
    start_date = models.DateField(_("event start date"), blank=True, null=True)
    end_date = models.DateField(_("event end date"), blank=True, null=True)
    
    # Location information
    venue_address = models.CharField(_("venue address"), max_length=300, blank=True, null=True)
    venue_name = models.CharField(_("venue name"), max_length=200, blank=True, null=True)
    specific_area = models.ForeignKey(AreaLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")  
    area_type = models.CharField(_("area type"), max_length=20, choices=EventAreaType.choices, default=EventAreaType.AREA)
    areas_involved = models.ManyToManyField(AreaLocation, blank=True, related_name="involved_in_events")  
    
    # Event details
    number_of_pax = models.IntegerField(_("number of participants"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    theme = models.CharField(_("event theme"), max_length=200, blank=True, null=True)
    anchor_verse = models.CharField(_("anchor verse"), max_length=200, blank=True, null=True)
    
    # Supervision
    supervising_chapter_youth_head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,  
        verbose_name="youth chapter head supervisor", related_name="supervised_events"  
    )
    supervising_chapter_CFC_coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,  
        verbose_name="youth CFC coordinator supervisor", related_name="cfc_supervised_events" 
    )

    # Service team
    service_team = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="EventServiceTeamMember", 
        through_fields=("event", "user"), 
        related_name="events_service_team", 
        blank=True
    )
    
    # ADDED: Useful methods
    def __str__(self):
        event_type = self.get_event_type_display()
        return f"{event_type}: {self.name or 'Unnamed Event'} ({self.start_date})" if self.start_date else f"{event_type}: {self.name or 'Unnamed Event'}"
    
    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

class EventServiceTeamMember(models.Model):
    '''
    Represents the ST member of an event (through model)
    '''
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="event_memberships")  
    event = models.ForeignKey("Event", on_delete=models.CASCADE, 
                                  related_name="service_team_members")
    
    roles = models.ManyToManyField("EventRole", blank=True, related_name="service_team_members")  
    head_of_role = models.BooleanField(default=False)

    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="assigned_event_members"  
    ) 
    
    class Meta:
        unique_together = ("user", "event") 
        verbose_name = _("Event Service Team Member")
        verbose_name_plural = _("Event Service Team Members")

    def __str__(self):
        role_names = ", ".join([str(role) for role in self.roles.all()])
        return f"ST: {self.user} → {role_names or 'No roles'} (by {self.assigned_by or 'system'})"
    
class EventRole(models.Model):
    '''
    Roles in Events
    '''
    class EventRoleTypes(models.TextChoices):
        ASSISTANT_TEAM_LEADER = "ASSISTANT_TEAM_LEADER", _("Assistant Team Leader")
        CAMP_SERVANT = "CAMP_SERVANT", _("Camp Servant")
        FACILITATOR = "FACILITATOR", _("Facilitator") 
        GAMES_MASTER = "GAMES_MASTER", _("Games Master")
        COUPLE_COORDINATOR = "COUPLE_COORDINATOR", _("Couple Coordinator") 
        SHARER = "SHARER", _("Sharer") 
        SPEAKER = "SPEAKER", _("Speaker") 
        TEAM_LEADER = "TEAM_LEADER", _("Team Leader") 
        WORSHIP_LEADER = "WORSHIP_LEADER", _("Worship Leader")
        TECH_SUPPORT = "TECH_SUPPORT", _("Tech Support") 
        YOUTH_OBSERVER = "YOUTH_OBSERVER", _("Youth Observer") 
        CFC_OBSERVER = "CFC_OBSERVER", _("CFC Observer") 
        CFC_HELPER = "CFC_HELPER", _("CFC Helper") 
        CFC_COORDINATOR = "CFC_COORDINATOR", _("Coordinator")
        SFC_HELPER = "SFC_HELPER", _("SFC Helper") 
        VOLUNTEER = "VOLUNTEER", _("Volunteer")
        ORGANIZER = "ORGANIZER", _("Organizer")
        # CONFERENCE LEVEL
        SECRETARIAT = "SECRETARIAT", _("Secretariat") 
        PROGRAMME = "PROGRAMME", _("Programme")
        PFO = "PFO", _("PFO")
        PRODUCTION = "PRODUCTION", _("Production")
        LOGISTICS = "LOGISTICS", _("Logistics")
        MUSIC_MINISTRY = "MUSIC_MINISTRY", _("Music Ministry") 
        LITURGY = "LITURGY", _("Liturgy")
        COMPETITIONS = "COMPETITIONS", _("Competitions")
        PROMOTIIONS = "PROMOTIONS", _("Promotions")
        DOCUMENTATION = "DOCUMENTATION", _("Documentation")      
        EVENT_HEADS = "EVENT_HEADS", _("Event_heads")
        GENERAL_SERVICES = "GENERAL_SERVICES", _("General Services")
        CATERING = "CATERING", _("Catering")
        
    role_name = models.CharField(
        _("role name"), max_length=50, choices=EventRoleTypes.choices,
        unique=True
    )
    
    description = models.TextField(_("role description"), blank=True, null=True)
    
    class Meta:
        verbose_name = _("Event Role")
        verbose_name_plural = _("Event Roles")
        ordering = ['role_name']
    
    def __str__(self):
        return self.get_role_name_display()
    
# EVENT PARTICIPANT MODELS
    
class EventParticipant(models.Model):
    '''
    Represents participants in events of various sizes
    '''
    class ParticipantStatus(models.TextChoices):
        REGISTERED = "REGISTERED", _("Registered")
        CONFIRMED = "CONFIRMED", _("Confirmed")
        ATTENDED = "ATTENDED", _("Attended")
        CANCELLED = "CANCELLED", _("Cancelled")
        WAITLISTED = "WAITLISTED", _("Waitlisted")
    
    class ParticipantType(models.TextChoices):
        PARTICIPANT = "PARTICIPANT", _("Participant")
        SERVICE_TEAM = "SERVICE_TEAM", _("Service_team")
        OBSERVER = "OBSERVER", _("Observer")
        GUEST = "GUEST", _("Guest")
        SPEAKER = "SPEAKER", _("Speaker")
        VOLUNTEER = "VOLUNTEER", _("Volunteer")
    
    # essential info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="participants")
    
    # if the user already exists in the database, then default to use this 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="event_participations", blank=True, null=True)
    guest_user = models.ForeignKey("GuestParticipant", on_delete=models.CASCADE, 
                            related_name="event_participations", blank=True, null=True)
    # Participant meta information
    participant_type = models.CharField(_("participant type"), max_length=20, 
                                      choices=ParticipantType.choices, default=ParticipantType.PARTICIPANT)
    status = models.CharField(_("status"), max_length=20, 
                             choices=ParticipantStatus.choices, default=ParticipantStatus.REGISTERED)
    
    # Registration details
    registration_date = models.DateTimeField(_("registration date"), auto_now_add=True)
    confirmation_date = models.DateTimeField(_("confirmation date"), blank=True, null=True)
    attended_date = models.DateTimeField(_("attended date"), blank=True, null=True)
    
    # Consent Details
    media_consent = models.BooleanField(default=False)
    data_consent = models.BooleanField(default=False)
    understood_registration = models.BooleanField(default=False)
    
    # Additional information
    dietary_restrictions = models.TextField(_("dietary restrictions"), blank=True, null=True)
    special_needs = models.TextField(_("special needs"), blank=True, null=True)
    emergency_contact = models.CharField(_("emergency contact"), max_length=200, blank=True, null=True)
    emergency_phone = models.CharField(_("emergency phone"), max_length=20, blank=True, null=True)
    
    # Payment information (if applicable)
    paid_amount = models.DecimalField(_("paid amount"), max_digits=10, decimal_places=2, default=0.00)
    payment_date = models.DateTimeField(_("payment date"), blank=True, null=True)
    payment_method = models.CharField(_("payment method"), max_length=50, blank=True, null=True)
    
    notes = models.TextField(_("notes"), blank=True, null=True)
    # further resources and memo
    resources = models.ManyToManyField("PublicEventResource", blank=True, related_name="event_resources")
    memo = models.ForeignKey(
        "PublicEventResource",
        verbose_name=_("main event memo"),
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name="event_memos"
        )
    
    class Meta:
        unique_together = ("event", "user")
        verbose_name = _("Event Participant")
        verbose_name_plural = _("Event Participants")
        ordering = ['registration_date']
    
    def __str__(self):
        return f"{self.user} - {self.event} ({self.get_status_display()})"
    
class GuestParticipant (models.Model):
    '''
    Represents a person coming to the event who isn't registered within the community, data can be used later to register into the
    community.
    '''
    # choice fields
    class ParticipantMinistryType(models.TextChoices):
        YFC = "YFC", _("Youth for Christ")
        CFC = "CFC", _("Couples for Christ")
        SFC = "SFC", _("Singles for Christ")
        KFC = "KFC", _("Kids for Christ")
        GUEST_YOUTH = "GTY", _("Guest Youth")
        GUEST_ADULT = "GTA", _("Guest Adult") 
        VOLUNTEER = "VLN", _("Volunteer")
        VISITOR = "VST", _("Visitor")
        OTHER = "OTH", _("Other")
        
    class GenderType(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", _("Prefer not to say")
        
    # location
    chapter = models.ManyToManyField(ChapterLocation, related_name="chapter_events", blank=True)
    outside_of_country = models.BooleanField(default=False)
    country_of_origin = models.ForeignKey(CountryLocation, on_delete=models.SET_NULL, blank=True, null=True)
    ministry_type = models.CharField(
        verbose_name=_("Family Ministry"), 
        choices=ParticipantMinistryType, 
        default=ParticipantMinistryType.GUEST_YOUTH,
        blank=True,
        null=True
        )
    
    email = models.EmailField(
        unique=True, 
        blank=True, 
        null=True,
        verbose_name=_("participant email address")
    )
    
    phone_number = models.CharField( 
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name=_("participant phone number"),
    )
    
    first_name = models.CharField(
        max_length=50,
        verbose_name=_("participant first name"),
        blank=True,
        null=True
    )
    
    last_name = models.CharField(
        max_length=50,
        verbose_name=_("participant last name"),
        blank=True,
        null=True
    )
    
    middle_name = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name=_("participant middle name")
    )
    
    preferred_name = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name=_("participant preferred name")
    )
    
    gender = models.CharField(
        max_length=20, 
        choices=GenderType.choices,
        verbose_name=_("participant gender"),
        blank=True,
        null=True
    )
    
    date_of_birth = models.DateField(
        verbose_name=_("participant date of birth"), 
        blank=True, 
        null=True,  
        help_text=_("Format: YYYY-MM-DD")
    )
    
    profile_picture = models.ImageField(
        upload_to="guest-event-profile-images/", 
        blank=True, 
        null=True,
        verbose_name=_("participant event profile picture")
    )
    
    alergies = models.ManyToManyField(
        Alergies, 
        verbose_name=_("Individual alergies"),
        related_name="user_alergies", 
        blank=True, 
        )
    
    further_alergy_information = models.TextField(
        verbose_name=_("other alergy information"), 
        blank=True, 
        null=True
        )
    
    emergency_contacts = models.ManyToManyField(
        EmergencyContact,
        verbose_name=_("Emergency contacts"),
        related_name="guest_user_emergency_contacts",
        blank=True
    )
    
# EVENT PROPER MODELS
    
class EventTalk(models.Model):
    '''
    Represents talks/sessions within an event
    '''
    class TalkType(models.TextChoices):
        TALK = "TALK", _("Talk")
        SHARING = "SHARING", _("Sharing")
        WORKSHOP = "WORKSHOP", _("Workshop")
        BREAKOUT = "BREAKOUT", _("Breakout Session")
        PLENARY = "PLENARY", _("Plenary Session")
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="talks")
    
    # Talk information
    title = models.CharField(_("talk title"), max_length=200)
    talk_type = models.CharField(_("talk type"), max_length=20, choices=TalkType.choices, default=TalkType.TALK)
    description = models.TextField(_("description"), blank=True, null=True)
    objective = models.TextField(_("objective"), blank=True, null=True)
    
    # Scheduling
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(_("end time"))
    duration_minutes = models.IntegerField(_("duration in minutes"), validators=[validators.MinValueValidator(1)])
    
    # Speaker information
    # TODO: Speakers must be registered within the community or guest speaker table too
    speaker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                               null=True, blank=True, related_name="event_talks")
    speaker_bio = models.TextField(_("speaker bio"), blank=True, null=True)
    
    # Location
    venue = models.CharField(_("venue"), max_length=200, blank=True, null=True)
    room = models.CharField(_("room"), max_length=100, blank=True, null=True)
    
    # Resources
    slides_url = models.URLField(_("slides URL"), blank=True, null=True)
    handout_url = models.URLField(_("handout URL"), blank=True, null=True)
    video_url = models.URLField(_("video URL"), blank=True, null=True)
    
    # Status
    is_published = models.BooleanField(_("is published"), default=True)
    
    class Meta:
        verbose_name = _("Event Talk")
        verbose_name_plural = _("Event Talks")
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.title} - {self.event.name}"

class EventWorkshop(models.Model):
    '''
    Represents workshops within an event
    '''
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="workshops")
    
    # Workshop information
    title = models.CharField(_("workshop title"), max_length=200)
    description = models.TextField(_("description"))
    objectives = models.TextField(_("learning objectives"))
    
    # Scheduling
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(_("end time"))
    duration_minutes = models.IntegerField(_("duration in minutes"), validators=[validators.MinValueValidator(1)])
    
    # Facilitators (workshop leader, etc)
    facilitators = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="facilitated_workshops", blank=True)
    primary_facilitator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                           null=True, blank=True, related_name="primary_workshops")
    
    # Capacity
    max_participants = models.IntegerField(_("maximum participants"), validators=[validators.MinValueValidator(1)])
    min_participants = models.IntegerField(_("minimum participants"), default=1, 
                                          validators=[validators.MinValueValidator(1)])
    
    # Location
    venue = models.CharField(_("venue"), max_length=200, blank=True, null=True)
    room = models.CharField(_("room"), max_length=100, blank=True, null=True)
    
    # Requirements
    prerequisites = models.TextField(_("prerequisites"), blank=True, null=True)
    materials_needed = models.TextField(_("materials needed"), blank=True, null=True)
    participant_preparation = models.TextField(_("participant preparation"), blank=True, null=True)
    
    # Resources
    resource_materials = models.TextField(_("resource materials"), blank=True, null=True)
    handout_url = models.URLField(_("handout URL"), blank=True, null=True)
    
    # Status
    is_published = models.BooleanField(_("is published"), default=True)
    is_full = models.BooleanField(_("is full"), default=False)
    
    class Meta:
        verbose_name = _("Event Workshop")
        verbose_name_plural = _("Event Workshops")
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.title} - {self.event.name}"
    
    @property
    def current_participant_count(self):
        # This would typically be implemented with a through model for workshop participants
        return 0  # Placeholder - you'd implement actual counting logic

class PublicEventResource(models.Model):
    '''
    represents a public resource e.g. a link to a further google form or a memo
    '''
    resource_name = models.CharField(verbose_name=_("public resource name"))
    resource_link = models.CharField(verbose_name=_("public resource link"), blank=True, null=True)
    resource_file = models.FileField(verbose_name=("file resource"), upload_to="public-event-resources")
    created_at = models.DateTimeField(auto_now_add=True)
    public_resource = models.BooleanField(default=False)
    

    