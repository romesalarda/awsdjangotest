from django.db import models
from django.core import validators
from .location_models import AreaLocation
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid
class YouthCamp(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class YouthCampAreaType(models.TextChoices):
        AREA = "AREA", _("Area")
        UNIT = "UNIT", _("Unit")
        CLUSTER = "CLUSTER", _("Cluster")    
        
    # Basic information
    name = models.CharField(_("camp name"), max_length=200, blank=True, null=True)  
    start_date = models.DateField(_("camp start date"), blank=True, null=True)
    end_date = models.DateField(_("camp end date"), blank=True, null=True)
    
    # Location information
    venue_address = models.CharField(_("venue address"), max_length=300, blank=True, null=True)
    venue_name = models.CharField(_("venue name"), max_length=200, blank=True, null=True)
    specific_area = models.ForeignKey(AreaLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name="youth_camps")  
    area_type = models.CharField(_("area type"), max_length=20, choices=YouthCampAreaType.choices, default=YouthCampAreaType.AREA)
    areas_involved = models.ManyToManyField(AreaLocation, blank=True, related_name="involved_in_camps")  
    
    # Camp details
    number_of_pax = models.IntegerField(_("number of participants"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    theme = models.CharField(_("camp theme"), max_length=200, blank=True, null=True)
    anchor_verse = models.CharField(_("anchor verse"), max_length=200, blank=True, null=True)
    
    # Supervision
    supervising_chapter_youth_head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,  
        verbose_name="youth chapter head supervisor", related_name="supervised_youth_camps"  
    )
    supervising_chapter_CFC_coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,  
        verbose_name="youth CFC coordinator supervisor", related_name="cfc_supervised_youth_camps" 
    )

    # Service team
    service_team = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="YouthCampServiceTeamMember", 
        through_fields=("youth_camp", "user"), 
        related_name="youth_camps_service_team", 
        blank=True
    )
    
    # ADDED: Useful methods
    def __str__(self):
        return f"{self.name or 'Unnamed Camp'} ({self.start_date})" if self.start_date else str(self.name or 'Unnamed Camp')
    
    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

class YouthCampServiceTeamMember(models.Model):
    '''
    represents the ST member of a youth-camp
    '''
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="youth_camp_memberships")  
    youth_camp = models.ForeignKey("YouthCamp", on_delete=models.CASCADE, 
                                  related_name="service_team_members")
    
    roles = models.ManyToManyField("YouthCampRole", blank=True, related_name="service_team_members")  
    head_of_role = models.BooleanField(default=False)

    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="assigned_youth_camp_members"  
    ) 
    
    class Meta:
        unique_together = ("user", "youth_camp") 
        verbose_name = _("Youth Camp Service Team Member")
        verbose_name_plural = _("Youth Camp Service Team Members")

    def __str__(self):
        role_names = ", ".join([str(role) for role in self.roles.all()])
        return f"ST: {self.user} → {role_names or 'No roles'} (by {self.assigned_by or 'system'})"
    
class YouthCampRole(models.Model):
    class YouthCampRoleTypes(models.TextChoices):
        ASSISTANT_TEAM_LEADER = "ASSISTANT_TEAM_LEADER", _("Assistant Team Leader")
        CAMP_SERVANT = "CAMP_SERVANT", _("Camp Servant")
        SECRETARIAT = "SECRETARIAT", _("Secretariat") 
        FACILITATOR = "FACILITATOR", _("Facilitator") 
        GAMES_MASTER = "GAMES_MASTER", _("Games Master")
        COUPLE_COORDINATOR = "COUPLE_COORDINATOR", _("Couple Coordinator") 
        MUSIC_MINISTRY = "MUSIC_MINISTRY", _("Music Ministry") 
        SHARER = "SHARER", _("Sharer") 
        SPEAKER = "SPEAKER", _("Speaker") 
        TEAM_LEADER = "TEAM_LEADER", _("Team Leader") 
        WORSHIP_LEADER = "WORSHIP_LEADER", _("Worship Leader")
        TECH_SUPPORT = "TECH_SUPPORT", _("Tech Support") 
        YOUTH_OBSERVER = "YOUTH_OBSERVER", _("Youth Observer") 
        CFC_OBSERVER = "CFC_OBSERVER", _("CFC Observer") 
        CFC_HELPER = "CFC_HELPER", _("CFC Helper") 
        SFC_HELPER = "SFC_HELPER", _("SFC Helper") 

    role_name = models.CharField(
        _("role name"), max_length=50, choices=YouthCampRoleTypes.choices,  # ADDED: max_length, .choices
        unique=True  # ADDED: should be unique
    )
    
    # ADDED: description field
    description = models.TextField(_("role description"), blank=True, null=True)
    
    class Meta:
        verbose_name = _("Youth Camp Role")
        verbose_name_plural = _("Youth Camp Roles")
        ordering = ['role_name']
    
    def __str__(self):
        return self.get_role_name_display() 