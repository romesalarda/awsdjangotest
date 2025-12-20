from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django.utils.text import slugify
from django.core import validators
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
        
class CountryLocation (models.Model):
    
    '''
    specific country internationally
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = CountryField(blank=True, null=True, unique=True) # only one country in the database
    general_sector = models.CharField(verbose_name="general world sector", choices=GeneralSectorType)
    specific_sector = models.CharField(verbose_name="specific world sector", choices=SpecificSectorType)
    
    def __str__(self):
        return f"{self.general_sector} -> {self.specific_sector} -> {self.country}"
    
class ClusterLocation (models.Model):
    '''
    clusters are specific to country - cluster head - major sections of the country
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster_id = models.CharField(verbose_name="cluster-name", max_length=2)
    world_location = models.ForeignKey(CountryLocation, on_delete=models.CASCADE, related_name="clusters")
    cluster_description = models.TextField(blank=True, null=True, help_text="description of the cluster location", max_length=400)
    active = models.BooleanField(verbose_name="is-active-cluster", default=True)
    number_of_parishes = models.IntegerField(verbose_name="number-of-parish-communities", default=0)
    established_date = models.DateField(verbose_name="established-date", blank=True, null=True, auto_now_add=True)
  
    def __str__(self):
        self.cluster_id = slugify(self.cluster_id.upper().strip())
        return f"{str(self.world_location)} -> Cluster {self.cluster_id}"
    
MAX_LENGTH_LOCATION_ID = 20
    
class ChapterLocation (models.Model):
    '''
    specific chapter - chapter head - general mass area
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    chapter_id = models.CharField(verbose_name="chapter-id", blank=True, null=True)
    chapter_name = models.CharField(verbose_name="name-of-chapter", max_length=150) # verbose and nice name
    chapter_code = models.CharField(verbose_name="chapter-code", max_length=3, null=True) # for id purposes
    cluster = models.ForeignKey(ClusterLocation, on_delete=models.CASCADE, related_name="chapters")
    
    email_contact = models.EmailField(verbose_name="chapter-contact-email", blank=True, null=True)
    phone_contact = models.CharField(verbose_name="chapter-contact-phone", max_length=15, blank=True, null=True)
    
    chapter_description = models.TextField(blank=True, null=True)
    active_members = models.IntegerField(verbose_name="number-of-active-members", default=0)
    number_of_parishes = models.IntegerField(verbose_name="number-of-parish-communities", default=0)
    active = models.BooleanField(verbose_name="is-active-chapter", default=True)
    established_date = models.DateField(verbose_name="established-date", blank=True, null=True, auto_now_add=True)

    youth_chapter_heads = models.ManyToManyField('users.CommunityUser', blank=True, related_name="youth_chapters")
    adult_coordinators = models.ManyToManyField('users.CommunityUser', blank=True, related_name="adult_coordinated_chapters")
    volunteers = models.ManyToManyField('users.CommunityUser', blank=True, related_name="volunteered_chapters")

    class Meta:
        unique_together = ("chapter_name", "cluster")
        
    def save(self, *args, **kwargs):
        if not self.chapter_id:
            super().save(*args, **kwargs)
            chapter_id = slugify(self.chapter_code).upper() # SOE-D20FAG2FSDS
            self.chapter_id = chapter_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(chapter_id)]
            
        self.chapter_name = slugify(self.chapter_name.capitalize().strip())
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.cluster} -> {self.chapter_name}"

class UnitLocation (models.Model):
    '''
    Chapter split into different units - unit head. Generally allows the chapter to be 
    split into more sections I.e. north, south, west, east, etc via letter
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    unit_id = models.CharField(verbose_name="unit-id", blank=True, null=True) # single letter/2
    unit_name = models.CharField(verbose_name="unit name", max_length=2, default="A")
    chapter = models.ForeignKey(ChapterLocation, on_delete=models.CASCADE, related_name="units")
 
    class Meta:
        unique_together = ("unit_name", "chapter")
        
    def save(self, *args, **kwargs):
        
        if not self.unit_id: # E.G. D-SOUTHEAST-D20FAG2FSDS
            unit_id = slugify(self.unit_name + "-" + self.chapter.chapter_name).upper() 
            self.unit_id = unit_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(unit_id)]
        self.unit_name = slugify(self.unit_name.upper().strip())
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.chapter} -> UNIT {self.unit_name}"
    
class AreaLocation (models.Model):
    '''
    Specific area - area head (smallest unit of location)
    
    Generally represents an Area where events are regularly held.
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # DB primary key
    area_id = models.CharField(verbose_name="area-id", blank=True, null=True) # unique area identifier (readable)
    area_name = models.CharField(verbose_name="name-of-area", max_length=150) # verbose and nice name
    area_code = models.CharField(verbose_name="area-code", max_length=3, unique=True, null=True) # for id purposes
    
    unit = models.ForeignKey(UnitLocation, on_delete=models.CASCADE, related_name="areas")
    general_address = models.CharField(max_length=50, help_text="general postcode/address", blank=True, null=True)
    location_description = models.TextField(blank=True, null=True, help_text="description of the area location", max_length=400)
    
    active_members = models.IntegerField(verbose_name="number-of-active-members", default=0, help_text="Number of active members in this area", 
                                         validators=[validators.MinValueValidator(0)]
                                         )
    active = models.BooleanField(verbose_name="is-active-area", default=True)
    parish_communities = models.IntegerField(verbose_name="number-of-parish-communities", default=0, help_text="Number of parish communities in this area", 
                                             validators=[validators.MinValueValidator(0)]
                                             )    
    class Meta:
        unique_together = ("area_name", "unit")
        
    def save(self, *args, **kwargs):
        if not self.area_id:
            if not self.area_code: # populate area code if not provided, but it is mandatory to set anyway
                self.area_code = self.area_name.upper()[:3]
            area_id = slugify(self.area_code + "-" + self.unit.chapter.chapter_name).upper() # E.G. FRM-SOUTHEAST-D20FAG2FSDS
            self.area_id = area_id + str(self.id)[:MAX_LENGTH_LOCATION_ID - len(area_id)]
        self.area_name = slugify(self.area_name.capitalize().strip())
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.unit} -> {self.area_name}"
    
# a unit have areas such as Frimley, Horsham, Worthing, Oxford which are active main areas, but dorking, redhill would be extra searches that would be under the specific
# area. 
class SearchAreaSupportLocation (models.Model):
    '''
    supports with smaller or other locations around the main area. E.g. Horsham would be the main area, but crawley, ifield, littlehaven, etc come under it.
    So people that query that location would then be referred to horsham as the nearest major location with events.
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    name = models.CharField(verbose_name=_("name of relative location"), max_length=100) 
    relative_area = models.ForeignKey(AreaLocation, on_delete=models.SET_NULL, null=True, related_name="relative_search_areas")
    
    def save(self, *args, **kwargs):
        self.name = slugify(self.name.capitalize().strip())
        return super().save(*args, **kwargs)

class EventVenue (models.Model):
    '''
    Represents the venue being used at the event
    '''
    class VenueType(models.TextChoices):
        ACCOMODATION = "ACCOMODATION", _("Accomodation")
        MAIN_VENUE = "MAIN_VENUE", _("Main Venue")
        SECONDARY_VENUE = "SECONDARY_VENUE", _("Secondary Venue")
        SPORTS_VENUE = "SPORTS_VENUE", _("Sports Venue")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    name = models.CharField(verbose_name=_("venue name"))
    address_line_1 = models.CharField(verbose_name=_("venue address line 1"), blank=True, null=True)
    address_line_2 = models.CharField(verbose_name=_("venue address line 2"), blank=True, null=True)
    address_line_3 = models.CharField(verbose_name=_("venue address line 2"), blank=True, null=True)
    postcode = models.CharField(verbose_name=_("venue address"), blank=True, null=True)
    max_allowed_people = models.IntegerField(verbose_name=_("max allowed people"), default=0)
    venue_type = models.CharField(verbose_name=_("type of venue"), choices=VenueType, default=VenueType.MAIN_VENUE)
    general_area = models.ForeignKey(AreaLocation, on_delete=models.SET_NULL, verbose_name=_("community general area"), related_name="event_venues", null=True, blank=True)
    primary_venue = models.BooleanField(verbose_name=_("is primary venue"), default=True, blank=True, null=True)
    
    contact_phone_number = models.CharField(verbose_name=_("contact phone number"), max_length=15, blank=True, null=True, validators=[validators.MinLengthValidator(3), validators.MaxLengthValidator(20)])
    contact_email = models.EmailField(verbose_name=_("contact email"), blank=True, null=True, validators=[validators.EmailValidator()])
    
    def __str__(self):
        return f"{self.name} ({self.venue_type})"
    
    @property
    def full_address(self):
        parts = [self.address_line_1, self.address_line_2, self.address_line_3, self.postcode]
        return ', '.join(part for part in parts if part)
    
    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        # ensure there is only one main venue
        if self.venue_type == self.VenueType.MAIN_VENUE and self.primary_venue:
            EventVenue.objects.filter(general_area=self.general_area, primary_venue=True).update(primary_venue=False)
        self.name = slugify(self.name.capitalize().strip())
        return super().save(force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)

