from django.db import models
from django.utils.translation import gettext_lazy as _

import uuid
class Alergies (models.Model):
    '''
    represents allergies
    '''
    alergy_name = models.CharField(verbose_name=_("name of alergy"), max_length=200)
    alergy_description = models.TextField(verbose_name=_("alergy description"), blank=True, null=True)
    
    class Meta:
        verbose_name_plural = _("Alergies")
    
    def __str__(self):
        return self.alergy_name
    
class EmergencyContact (models.Model):
    '''
    Represents emergency contact of an individual
    '''
    id = models.UUIDField(verbose_name=_("emergency contact id"), default=uuid.uuid4, editable=False, primary_key=True)

    class ContactRelationshipType (models.TextChoices):
        MOTHER = "MOTHER", _("Mother")
        FATHER = "FATHER", _("Father")
        GUARDIAN = "GUARDIAN", _("Guardian")
        SPOUSE = "SPOUSE", _("Spouse")
        HUSBAND = "HUSBAND", _("Husband")
        WIFE = "WIFE", _("Wife")
        BROTHER = "BROTHER", _("Brother")
        SISTER = "SISTER", _("Sister")

    
    first_name = models.CharField(
        max_length=50,
        verbose_name=_("first name")
    )
    
    last_name = models.CharField(
        max_length=50,
        verbose_name=_("last name")
    )
    
    middle_name = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name=_("middle name")
    )
    
    preferred_name = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name=_("preferred name")
    )
    
    email = models.EmailField(
        unique=True, 
        blank=True, 
        null=True,
        verbose_name=_("emergency contact email address")
    )
    
    phone_number = models.CharField( 
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name=_("emergency contact phone number")
    )
    
    contact_relationship = models.CharField(
        verbose_name=_("emergency contact relationship"), blank=True, null=True, choices=ContactRelationshipType)