from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django.utils.text import slugify

import uuid


class GeneralSectorType(models.TextChoices):
    EUROPE = "EUROPE", _("Europe")
    ASIA = "ASIA", _("Asia")
    NORTH_AMERICA = "NORTH_AMERICA", _("North America")
    CENTRAL_AMERICA = "CENTRAL_AMERICA", _("Central America")
    SOUTH_AMERICA = "SOUTH_AMERICA", _("South America")
    AFRICA = "AFRICA", _("Africa")
    OCEANIA = "OCEANIA", _("Oceania")
    MIDDLE_EAST = "MIDDLE_EAST", _("Middle East")


class SpecificSectorType(models.TextChoices):
    # --- Europe ---
    NORTH_EUROPE = "NORTH_EUROPE", _("Northern Europe")
    SOUTH_EUROPE = "SOUTH_EUROPE", _("Southern Europe")
    WEST_EUROPE = "WEST_EUROPE", _("Western Europe")
    EAST_EUROPE = "EAST_EUROPE", _("Eastern Europe")
    CENTRAL_EUROPE = "CENTRAL_EUROPE", _("Central Europe")

    # --- Asia ---
    EAST_ASIA = "EAST_ASIA", _("East Asia")
    SOUTH_ASIA = "SOUTH_ASIA", _("South Asia")
    SOUTHEAST_ASIA = "SOUTHEAST_ASIA", _("Southeast Asia")
    CENTRAL_ASIA = "CENTRAL_ASIA", _("Central Asia")
    WEST_ASIA = "WEST_ASIA", _("Western Asia")  # overlaps with Middle East

    # --- Americas ---
    NORTH_AMERICA = "NORTH_AMERICA", _("North America")
    CENTRAL_AMERICA = "CENTRAL_AMERICA", _("Central America")
    CARIBBEAN = "CARIBBEAN", _("Caribbean")
    SOUTH_AMERICA_NORTH = "SOUTH_AMERICA_NORTH", _("Northern South America")
    SOUTH_AMERICA_SOUTH = "SOUTH_AMERICA_SOUTH", _("Southern South America")
    ANDES = "ANDES", _("Andean Region")
    CONO_SUR = "CONO_SUR", _("Cono Sur (Southern Cone)")

    # --- Africa ---
    NORTH_AFRICA = "NORTH_AFRICA", _("North Africa")
    WEST_AFRICA = "WEST_AFRICA", _("West Africa")
    EAST_AFRICA = "EAST_AFRICA", _("East Africa")
    CENTRAL_AFRICA = "CENTRAL_AFRICA", _("Central Africa")
    SOUTH_AFRICA = "SOUTH_AFRICA", _("Southern Africa")

    # --- Oceania ---
    AUSTRALIA_NEWZEALAND = "AUSTRALIA_NEWZEALAND", _("Australia & New Zealand")
    MELANESIA = "MELANESIA", _("Melanesia")
    MICRONESIA = "MICRONESIA", _("Micronesia")
    POLYNESIA = "POLYNESIA", _("Polynesia")

    # --- Middle East (can also overlap with West Asia) ---
    GULF = "GULF", _("Gulf States")
    LEVANT = "LEVANT", _("Levant")
    PERSIAN = "PERSIAN", _("Persian Region")
    
# TODO: to add european heads? not sure if that is a thing
    
class CountryLocation (models.Model):
    
    '''
    national head
    '''
    
    country = CountryField(blank=True, null=True, unique=True) # only one country in the database
    general_sector = models.CharField(verbose_name="general world sector", choices=GeneralSectorType)
    specific_sector = models.CharField(verbose_name="specific world sector", choices=SpecificSectorType)
    
    def __str__(self):
        return f"{self.general_sector} -> {self.specific_sector} -> {self.country}"
    
class ClusterLocation (models.Model):
    '''
    clusters are specific to country - cluster head
    '''
    cluster_id = models.CharField(verbose_name="cluster-name", max_length=2)
    world_location = models.ForeignKey(CountryLocation, on_delete=models.CASCADE, related_name="clusters")
    
    def __str__(self):
        return f"{str(self.world_location)} -> Cluster {self.cluster_id}"
    
MAX_LENGTH_LOCATION_ID = 20
    
class ChapterLocation (models.Model):
    '''
    specific chapter - chapter head
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    chapter_id = models.CharField(verbose_name="chapter-id", blank=True, null=True)
    chapter_name = models.CharField(verbose_name="name-of-chapter", max_length=150) # verbose and nice name
    chapter_code = models.CharField(verbose_name="chapter-code", max_length=3, null=True) # for id purposes
    cluster = models.ForeignKey(ClusterLocation, on_delete=models.CASCADE, related_name="chapters")
    
    class Meta:
        unique_together = ("chapter_name", "cluster")
        
    def save(self, *args, **kwargs):
        
        if not self.chapter_id:
            chapter_id = slugify(self.chapter_code).upper() # SOE-D20FAG2FSDS
            self.chapter_id = chapter_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(chapter_id)]
          
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.cluster} -> {self.chapter_name}"

class UnitLocation (models.Model):
    '''
    chapter split into different units - unit head
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    unit_id = models.CharField(verbose_name="unit-id", blank=True, null=True) # single letter/2
    unit_name = models.CharField(verbose_name="unit name", max_length=2)
    chapter = models.ForeignKey(ChapterLocation, on_delete=models.CASCADE, related_name="units")
    
    class Meta:
        unique_together = ("unit_name", "chapter")
        
    def save(self, *args, **kwargs):
        
        if not self.unit_id: # E.G. D-SOUTHEAST-D20FAG2FSDS
            unit_id = slugify(self.unit_name + "-" + self.chapter.chapter_name).upper() 
            self.unit_id = unit_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(unit_id)]
          
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.chapter} -> UNIT {self.unit_name}"
    
class AreaLocation (models.Model):
    '''
    specific area - area head (smallest unit of location)
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    area_id = models.CharField(verbose_name="area-id", blank=True, null=True)
    area_name = models.CharField(verbose_name="name-of-area", max_length=150)
    area_code = models.CharField(verbose_name="area-code", max_length=3, unique=True, null=True)
    unit = models.ForeignKey(UnitLocation, on_delete=models.CASCADE, related_name="areas")
    general_address = models.CharField(max_length=100, help_text="general postcode/address")
    location_description = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ("area_name", "unit")
        
    def save(self, *args, **kwargs):
        
        if not self.area_id:
            if not self.area_code: # populate area code if not provided, but it is mandatory to set anyway
                self.area_code = self.area_name.upper()[:3]
            area_id = slugify(self.area_code + "-" + self.unit.chapter.chapter_name).upper() # E.G. FRM-SOUTHEAST-D20FAG2FSDS
            self.area_id = area_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(area_id)]
          
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.unit} -> {self.area_name}"