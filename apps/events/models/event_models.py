from datetime import timedelta
from django.db import models
from django.core import validators
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .location_models import (
    AreaLocation, ChapterLocation, EventVenue)
import uuid

MAX_LENGTH_EVENT_NAME_CODE = 5

# TODO: add model for event organisers E.g. cfcyfcuk.nationalevents@gmail.com or cfcyfcuk.southeast@gmail.com

class EventResource(models.Model):
    '''
    represents a resource e.g. a link to a further google form or a memo
    '''
    class ResourceType (models.TextChoices): # TODO add this as a field
        LINK = "LINK", _("Link")
        PDF = "PDF", _("pdf")
        FILE = "FILE", _("File")
        PHOTO = "PHOTO", _("Photo")
        SOCIAL_MEDIA = "SOCIAL_MEDIA", _("Social Media")

    id = models.UUIDField(verbose_name=_("resource id"), default=uuid.uuid4, editable=False, primary_key=True)
    resource_name = models.CharField(verbose_name=_("public resource name"))
    # types
    resource_link = models.CharField(verbose_name=_("public resource link"), blank=True, null=True)
    resource_file = models.FileField(verbose_name=("file resource"), upload_to="public-event-file-resources", blank=True, null=True)
    image = models.FileField(verbose_name=("image resource"), upload_to="public-event-image-resources", blank=True, null=True)
    
    description = models.TextField(verbose_name=_("resource description"), max_length=500, blank=True, null=True)
    word_descriptor = models.TextField(verbose_name=_("word description"), max_length=100, blank=True, null=True, help_text=_("A word I.e. schedule or map"))

    created_at = models.DateTimeField(auto_now_add=True)
    public_resource = models.BooleanField(default=False)
    
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        verbose_name=_("resource added by"), null=True) # must be provided
    chapter_ownership = models.ForeignKey(
        ChapterLocation, on_delete=models.SET_NULL, 
        verbose_name=_("chapter that owns resource"), null=True, blank=True
        )

    # if used for events, can be gatekept until data is available
    release_date = models.DateTimeField(verbose_name=_("resource release date"), blank=True, null=True)
    expiry_date = models.DateTimeField(verbose_name=_("resource expiry date"), blank=True, null=True)
    

class Event(models.Model):
    '''
    Represents various types of events in the YFC Community
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class EventType(models.TextChoices):
        YOUTH_CAMP = "YOUTH_CAMP", _("YYC")
        CONFERENCE = "CONFERENCE", _("CNF")
        RETREAT = "RETREAT", _("RTR")
        WORKSHOP = "WORKSHOP", _("WKS")
        TRAINING = "TRAINING", _("TRN")
        PFO = "PFO", _("PFO")
        HOUSEHOLD = "HOUSEHOLD", _("HLD")
        FELLOWSHIP = "FELLOWSHIP", _("FLS")
        OTHER = "OTHER", _("OTH")
        
    class EventAreaType(models.TextChoices):
        AREA = "AREA", _("Area")
        UNIT = "UNIT", _("Unit")
        CLUSTER = "CLUSTER", _("Cluster") 
        NATIONAL = "NATIONAL", _("National")
        CONTINENTAL = "CONTINENTAL", _("Continental")
        INTERNATIONAL = "INTERNATIONAL", _("International")   
        
    # Event type and basic information
    event_type = models.CharField(_("event type"), max_length=20, choices=EventType.choices, default=EventType.YOUTH_CAMP)
    event_code = models.CharField(_("event code"), blank=True, null=True, 
                                  help_text=_("Event code that is shared around and for participant convenience. E.g. CNF26ANCRD - tells you it's a conference in 2026 with the name ANCHORED")
                                  ) # CNF26ANCRD
    
    description = models.TextField(verbose_name=_("event description"), blank=True, null=True) 
    sentence_description = models.CharField(
        verbose_name=_("sentence description"), blank=True, null=True, max_length=300,
        help_text=_("A brief one-sentence description of the event, for promotional purposes. E.g. A youth camp to anchor our faith in Christ.")
        ) 
    important_information = models.TextField(verbose_name=_("important information"), blank=True, null=True)
    what_to_bring = models.TextField(verbose_name=_("what to bring"), blank=True, null=True)
    landing_image = models.ImageField(        
        upload_to="event-landing-images/", 
        blank=True, 
        null=True,
        verbose_name=_("event landing image"))
    is_public = models.BooleanField(verbose_name=_("is event public"), default=False, null=True)
    
    name = models.CharField(_("event name"), max_length=200, null=True) # ANCHORED
    name_code = models.CharField( # simplified version of the name of the event
        _("event name code"), max_length=MAX_LENGTH_EVENT_NAME_CODE, 
        blank=True, null=True,
        validators=[
            validators.MaxLengthValidator(MAX_LENGTH_EVENT_NAME_CODE)
        ],
        help_text=_("Short code for the event name, used in generating the event code E.g. for ANCHORED event, use ANCRD")
        ) # ANCRD
    
    start_date = models.DateTimeField(_("event start date"), blank=True, null=True) # TODO: make this required 
    end_date = models.DateTimeField(_("event end date"), blank=True, null=True) 
    
    # Location information
    area_type = models.CharField(verbose_name=_("area type"), max_length=20, choices=EventAreaType.choices, default=EventAreaType.AREA)
    venues = models.ManyToManyField(EventVenue, blank=True, verbose_name=_("venues involved"))
    areas_involved = models.ManyToManyField(AreaLocation, blank=True, related_name="involved_in_events") # community areas involved, either nationally or locally
    
    # Pastoral Event details
    number_of_pax = models.IntegerField(_("number of participants"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    theme = models.CharField(_("event theme"), max_length=200, blank=True, null=True)
    anchor_verse = models.CharField(_("anchor verse"), max_length=200, blank=True, null=True)
    age_range = models.CharField(_("age range"), max_length=100, blank=True, null=True, help_text=_("E.g. 11-30"))
    expected_attendees = models.IntegerField(_("expected attendees"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    maximum_attendees = models.IntegerField(_("maximum attendees"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    # marks users that are able to view this event
    supervising_youth_heads = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,  
        verbose_name=_("youth chapter head supervisors"), related_name="supervised_events"
    )
    supervising_CFC_coordinators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        verbose_name=_("youth CFC coordinator supervisors"), related_name="cfc_supervised_events"
    )   
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_events",
        )

    # Service team
    service_team = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="EventServiceTeamMember", 
        through_fields=("event", "user"), 
        related_name="events_service_team", 
        blank=True
    )
    
    # important information
    resources = models.ManyToManyField(EventResource, blank=True, related_name="event_resources") # extra memos, photos promoting the event, etcs
    memo = models.ForeignKey(
        EventResource,
        verbose_name=_("main event memo"),
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name="event_memos"
        )
    notes = models.TextField(verbose_name=_("event notes"), blank=True, null=True)
    approved = models.BooleanField(verbose_name=_("event approved"), default=False)
    # registration dates
    registration_open = models.BooleanField(verbose_name=_("is registration open"), default=False)
    registration_open_date = models.DateTimeField(verbose_name=_("registration open date"), blank=True, null=True, auto_now=True)
    registration_deadline = models.DateTimeField(verbose_name=_("registration deadline"), blank=True, null=True)
    payment_deadline = models.DateTimeField(verbose_name=_("payment deadline"), blank=True, null=True)
    
    class EventStatus(models.TextChoices):
        PLANNING = "PLANNING", _("Planning")
        CONFIRMED = "CONFIRMED", _("Confirmed")
        ONGOING = "ONGOING", _("Ongoing")
        COMPLETED = "COMPLETED", _("Completed")
        CANCELLED = "CANCELLED", _("Cancelled")
        POSTPONED = "POSTPONED", _("Postponed") 
        
    status = models.CharField(_("event status"), max_length=20, choices=EventStatus.choices, default=EventStatus.PLANNING)  
    
    auto_approve_participants = models.BooleanField(verbose_name=_("auto approve participants"), default=False)
    
    def save(self, *args, **kwargs):
        if not self.event_code:
            if not self.name_code:
                self.name_code = self.name.upper()[:MAX_LENGTH_EVENT_NAME_CODE]
            self.event_code = f"{self.get_event_type_display()}{str(self.start_date.year)}{self.name_code}"
            
        if not self.duration_days and self.start_date and self.end_date:
            self.duration_days = (self.end_date - self.start_date).days + 1
        
        return super().save(*args, **kwargs)
    
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
    id = models.UUIDField(verbose_name=_("serivce team member id"), default=uuid.uuid4, editable=False, primary_key=True)
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
        return f"ST: {self.user}"
    
class EventRole(models.Model):
    '''
    Event roles that can be assigned to service team members - Global use for reference
    '''
    id = models.UUIDField(verbose_name=_("event role id"), default=uuid.uuid4, editable=False, primary_key=True)

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
    
# * EVENT PARTICIPANT MODELS
    
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
    # unique participant ID for the event - basically their reference number
    # event code + unique uuid of this participant object
    event_pax_id = models.CharField(verbose_name=_("Participant ID"), blank=True, null=True)
    
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="participants")
    
    # if the user already exists in the database, then default to use this 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
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
    terms_and_conditions_consent = models.BooleanField(default=False)
    news_letter_consent = models.BooleanField(default=False)

    # Payment information (if applicable)
    paid_amount = models.DecimalField(_("paid amount"), max_digits=10, decimal_places=2, default=0.00)
    payment_date = models.DateTimeField(_("most recent payment date"), blank=True, null=True)
    
    notes = models.TextField(_("notes"), blank=True, null=True)
    verified = models.BooleanField(verbose_name=_("participant approved"), default=False) # set to true when payments paid and they are approved to attend
    
    accessibility_requirements = models.TextField(_("accessibility requirements"), blank=True, null=True)
    special_requests = models.TextField(_("special requests"), blank=True, null=True)
    
    
    class Meta:
        verbose_name = _("Event Participant")
        verbose_name_plural = _("Event Participants")
        ordering = ['registration_date']
        
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_event_user_participation"
            ),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.event} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # TODO: if this is a premature save (i.e. no id yet), then save first and then update the event_pax_id
        if not self.id:
            super().save(*args, **kwargs)  # Save first to get an ID
            
        if not self.event_pax_id:
            # Save first to get an ID
            self.event_pax_id = f"{self.event.event_code}-{self.id}".upper()
            while EventParticipant.objects.filter(event_pax_id=self.event_pax_id).exists():
                self.id = uuid.uuid4()
                self.event_pax_id = f"{self.event.event_code}-{self.id}".upper()
            if len(self.event_pax_id) > 20:
                self.event_pax_id = self.event_pax_id[:20]  
        super().save(*args, **kwargs)

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

class EventDayAttendance (models.Model):
    '''
    Represents attendance records for events
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="attendance_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_attendance")
    
    day_date = models.DateField(_("attendance day"), blank=True, null=True)
    day_id = models.IntegerField(_("day id"), validators=[validators.MinValueValidator(1)])
    
    check_in_time = models.TimeField(_("check-in time"), blank=True, null=True)
    check_out_time = models.TimeField(_("check-out time"), blank=True, null=True)
    
    class Meta:
        verbose_name = _("Event Day Attendance")
        verbose_name_plural = _("Event Day Attendances")
        unique_together = ("event", "user", "check_in_time", "day_id")
        ordering = ['-check_in_time']
    
    def __str__(self):
        return f"Attendance: {self.user} - {self.event.name}"

    @property
    def duration(self):
        if self.check_in_time and self.check_out_time:
            return self.check_out_time - self.check_in_time
        return None
    
    def save(self, *args, **kwargs):
        if self.day_date is None and self.check_in_time:
            # pull start date from event + the day id and set that to date
            event_start_date = self.event.start_date.date() if self.event.start_date else None
            if event_start_date:
                self.day_date = event_start_date + timedelta(days=self.day_id - 1)
                
                
        return super().save(*args, **kwargs)