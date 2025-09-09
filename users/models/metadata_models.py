from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

import uuid

class Alergies (models.Model):
    '''
    represents allergies
    '''
    name = models.CharField(max_length=200, verbose_name=_("name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("description"))
    instructions = models.TextField(blank=True, null=True, verbose_name=_("instructions"))
    triggers = models.TextField(blank=True, null=True, verbose_name=_("triggers (e.g., peanuts, pollen)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("last updated"))
    
    class Severity(models.TextChoices):
        MILD = "MILD", _("Mild")
        MODERATE = "MOD", _("Moderate")
        SEVERE = "SEV", _("Severe")
        CRITICAL = "CRT", _("Critical")

    severity = models.CharField(
        max_length=5,
        choices=Severity.choices,
        default=Severity.MILD,
        verbose_name=_("severity level")
    )
    
    class Meta:
        verbose_name_plural = _("Alergies")
    
    def __str__(self):
        return self.name
    
class MedicalConditions (models.Model):
    '''
    represents medical
    '''
    name = models.CharField(max_length=200, verbose_name=_("name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("description"))
    instructions = models.TextField(blank=True, null=True, verbose_name=_("instructions"))
    triggers = models.TextField(blank=True, null=True, verbose_name=_("triggers (e.g., peanuts, pollen)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("last updated"))
    
    class Severity(models.TextChoices):
        MILD = "MILD", _("Mild")
        MODERATE = "MOD", _("Moderate")
        SEVERE = "SEV", _("Severe")
        CRITICAL = "CRT", _("Critical")

    severity = models.CharField(
        max_length=5,
        choices=Severity.choices,
        default=Severity.MILD,
        verbose_name=_("severity level")
    )
    
    class Meta:
        verbose_name_plural = _("Medical Conditions")
    
    def __str__(self):
        return self.name
    
class EmergencyContact (models.Model):
    '''
    Represents emergency contact of an individual
    '''
    id = models.UUIDField(verbose_name=_("emergency contact id"), default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
        verbose_name=_("linked user in the community"), null=True, blank=True,
        related_name="community_user_emergency_contacts"
        ) # better if we can use an existing member in the community, if not fill the details below

    class ContactRelationshipType(models.TextChoices):
        MOTHER = "MOTHER", _("Mother")
        FATHER = "FATHER", _("Father")
        GUARDIAN = "GUARDIAN", _("Guardian")
        SPOUSE = "SPOUSE", _("Spouse")
        HUSBAND = "HUSBAND", _("Husband")
        WIFE = "WIFE", _("Wife")
        BROTHER = "BROTHER", _("Brother")
        SISTER = "SISTER", _("Sister")
        FRIEND = "FRIEND", _("Friend")
        OTHER = "OTHER", _("Other")

    first_name = models.CharField(max_length=50,verbose_name=_("first name"))
    last_name = models.CharField(max_length=50,verbose_name=_("last name"))
    middle_name = models.CharField(max_length=50, blank=True, null=True,verbose_name=_("middle name"))
    
    preferred_name = models.CharField(max_length=50, blank=True, null=True,verbose_name=_("preferred name"))
    email = models.EmailField(blank=True, null=True, verbose_name=_("email address"))
    phone_number = models.CharField(max_length=20,blank=True,null=True, verbose_name=_("emergency contact phone number")) 
    secondary_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("secondary phone number"))

    contact_relationship = models.CharField(
        max_length=20,
        choices=ContactRelationshipType.choices,
        verbose_name=_("relationship"),
        blank=True,
        null=True,
    )
    
    address = models.TextField(blank=True, null=True, verbose_name=_("address"))
    is_primary = models.BooleanField(default=False, verbose_name=_("primary emergency contact"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("additional notes"))
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.contact_relationship or _('Contact')})"