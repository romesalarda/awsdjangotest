from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

import uuid

class Allergy(models.Model):
    """Represents allergy definitions (master data)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name=_("name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("description"))
    triggers = models.TextField(blank=True, null=True, verbose_name=_("triggers (e.g., peanuts, pollen)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("last updated"))

    class Meta:
        verbose_name_plural = _("Allergies")

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        self.name = self.name.title()
        return super().save(*args, **kwargs)


class MedicalCondition(models.Model):
    """Represents medical condition definitions (master data)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name=_("name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("description"))
    triggers = models.TextField(blank=True, null=True, verbose_name=_("triggers (e.g., pollen, dust)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("last updated"))

    class Meta:
        verbose_name_plural = _("Medical Conditions")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.title()
        return super().save(*args, **kwargs)

class UserAllergy(models.Model):
    """Join model with user-specific allergy info."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_allergies"
    )
    allergy = models.ForeignKey(
        "Allergy",
        on_delete=models.CASCADE,
        related_name="user_links"
    )

    class Severity(models.TextChoices):
        MILD = "MILD", _("Mild")
        MODERATE = "MODERATE", _("Moderate")
        SEVERE = "SEVERE", _("Severe")
        CRITICAL = "CRITICAL", _("Critical")

    severity = models.CharField(
        max_length=8,
        choices=Severity.choices,
        default=Severity.MILD
    )
    instructions = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "allergy")

    def __str__(self):
        return f"{self.user} - {self.allergy} ({self.severity})"


class UserMedicalCondition(models.Model):
    """Join model with user-specific medical condition info."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_medical_conditions"
    )
    condition = models.ForeignKey(
        "MedicalCondition",
        on_delete=models.CASCADE,
        related_name="user_links"
    )

    class Severity(models.TextChoices):
        MILD = "MILD", _("Mild")
        MODERATE = "MODERATE", _("Moderate")
        SEVERE = "SEVERE", _("Severe")
        CRITICAL = "CRITICAL", _("Critical")

    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.MILD
    )
    instructions = models.TextField(blank=True, null=True)
    date_diagnosed = models.DateField(blank=True, null=True)

    class Meta:
        unique_together = ("user", "condition")

    def __str__(self):
        return f"{self.user} - {self.condition} ({self.severity})"

    
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

    def save(self, *args, **kwargs):
        # normalise
        self.first_name = self.first_name.title()
        if self.last_name:
            self.last_name = self.last_name.title()
        if self.middle_name:
            self.middle_name = self.middle_name.title()
        if self.preferred_name:
            self.preferred_name = self.preferred_name.title() 
        
        return super().save(*args, **kwargs)
