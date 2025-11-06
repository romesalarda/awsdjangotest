from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core import validators
import uuid

class Organisation(models.Model):
    '''
    Represents an organisation e.g. ANCOP, CFC-YFC Community
    '''
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(verbose_name=_("organisation name"), max_length=100)
    description = models.CharField(verbose_name=_("organisation description"), blank=True, null=True)
    
    landing_image = models.ImageField(        
        upload_to="organisations/landing-images/", 
        blank=True, 
        null=True,
        verbose_name=_("organisation landing image"))
    
    logo = models.ImageField(        
        upload_to="organisations/logos/", 
        blank=True, 
        null=True,
        verbose_name=_("organisation logo"))
    
    email = models.CharField(verbose_name=_("organsiation email"), max_length=100, blank=True, null=True)
    external_link = models.CharField(verbose_name=_("organsiation website link"), max_length=100, blank=True, null=True)
    
    def __str__(self):
        return self.name

class OrganisationSocialMediaLink(models.Model):
    '''
    Represents link for organisations
    '''
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(verbose_name=_("organisation social media type"), max_length=100)
    external_link = models.CharField(verbose_name=_("organsiation website link"), max_length=100)
    description = models.CharField(verbose_name=_("organisation description"), blank=True, null=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="social_media_links")
    
    def __str__(self):
        return "(%s) %s" % (self.organisation.name, self.name)
