from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator, EmailValidator, RegexValidator

import datetime
import uuid

from .user_manager import CommunityUserManager

MAX_MEMBER_ID_LENGTH = 20
MAX_MEMBER_ID_FIRST_NAME = 5
MAX_MEMBER_ID_LAST_NAME = 5

class CommunityUser(AbstractBaseUser, PermissionsMixin):
    '''
    Main AUTH class to authenticate users, all users signing in for events must have an account
    '''
    class MinistryType(models.TextChoices):
        YFC = "YFC", _("Youth for Christ")
        CFC = "CFC", _("Couples for Christ")
        SFC = "SFC", _("Singles for Christ")
        KFC = "KFC", _("Kids for Christ")
        
        VOLUNTEER = "VLN", _("Volunteer") # not looking to join the community but is attending an event e.g. a priest
        YOUTH_GUEST = "YGT", _("Youth Guest")
        ADULT_GUEST = "AGT", _("Adult Guest") 
        
    class GenderType(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        
    class MaritalType(models.TextChoices):     # TODO: DEPRECATE
        SINGLE = "SINGLE", _("Single")
        MARRIED = "MARRIED", _("Married")
        WIDOWED = "WIDOWED", _("Widowed")
        
    class BloodType(models.TextChoices):     # TODO: DEPRECATE
        A_POS = "A+", _("A Positive")
        A_NEG = "A-", _("A Negative")
        B_POS = "B+", _("B Positive")
        B_NEG = "B-", _("B Negative")
        AB_POS = "AB+", _("AB Positive")
        AB_NEG = "AB-", _("AB Negative")
        O_POS = "O+", _("O Positive")
        O_NEG = "O-", _("O Negative")

    # auth information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # ! hidden do not show
    member_id = models.CharField(max_length=100, unique=True, editable=False,verbose_name=_("member ID"))
    username = models.CharField(max_length=100, unique=True, verbose_name=_("username"))
    # contact information
    primary_email = models.EmailField(unique=True, blank=True, null=True,verbose_name=_("primary email address"), validators=[EmailValidator()])
    secondary_email = models.EmailField(unique=True, blank=True, null=True,verbose_name=_("secondary email address"), validators=[EmailValidator()])
    phone_number = models.CharField(max_length=20,blank=True,null=True, verbose_name=_("phone number"))
    
    # identity information
    first_name = models.CharField(max_length=50,verbose_name=_("first name"))
    last_name = models.CharField(max_length=50,verbose_name=_("last name"))
    middle_name = models.CharField(max_length=50,blank=True, null=True,verbose_name=_("middle name"))
    preferred_name = models.CharField(max_length=50, blank=True, null=True,verbose_name=_("preferred name"))
    gender = models.CharField(max_length=6, choices=GenderType.choices, blank=True, null=True, verbose_name=_("gender"))
    age = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0), MaxValueValidator(150)],verbose_name=_("age"))
    date_of_birth = models.DateField(verbose_name=_("date of birth"), blank=True, null=True,  help_text=_("Format: YYYY-MM-DD"))
    
    # location information
    area_from = models.ForeignKey("events.AreaLocation", on_delete=models.SET_NULL, 
                                  verbose_name=_("area of residence"), blank=True, null=True
                                  )
    # auth checks
    is_active = models.BooleanField(default=True,verbose_name=_("active")) # able to login
    is_staff = models.BooleanField(default=False,verbose_name=_("staff status")) # able to access django admin
    is_encoder = models.BooleanField(default=False,verbose_name=_("encoder status")) # able to create events but not django admin
    
    # profile information
    profile_picture = models.ImageField(
        upload_to="user-profile-images/", 
        blank=True, 
        null=True,
        verbose_name=_("user profile picture")
    )
    profile_picture_uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("profile picture uploaded at")
    )   
    
    # safeguarding information
    allergies = models.ManyToManyField(
        "Allergy",
        through="UserAllergy",
        related_name="allergy_users",
        blank=True
    )

    medical_conditions = models.ManyToManyField(
        "MedicalCondition",
        through="UserMedicalCondition",
        related_name="condition_users",
        blank=True
    )
        
    # service information
    community_roles = models.ManyToManyField(
        "CommunityRole",         
        through="UserCommunityRole",
        through_fields=("user", "role"),
        related_name="user_community_roles", 
        help_text=_("role/s in the community"), 
        blank=True
    )
    ministry = models.CharField(
        max_length=3, 
        choices=MinistryType.choices,  
        default=MinistryType.YOUTH_GUEST,
        verbose_name=_("ministry")
    ) 
    
    user_uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("user uploaded to database at")
    )
    
    # helper fields
    notes = models.TextField(verbose_name=_("user notes (admin use)"), blank=True, null=True)
    
    # MODEL PROPER
    
    objects = CommunityUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name"]  # Removed password and username from required fields for registration
    
    class Meta:
        verbose_name = _("community user")
        verbose_name_plural = _("community users")
        # REMOVED: unique_together for first_name/last_name as it's too restrictive
        ordering = ["last_name", "first_name"]


    def save(self, *args, **kwargs):
        # Track if this is a new instance (needs member_id generation)
        # is_new_instance = self.pk is None
        needs_member_id = not self.member_id
        
        # Ensure username is unique
    
        if not self.username: 
            base_username = slugify(f"{self.ministry}-{self.first_name}{self.last_name}").upper()
            self.username = base_username
        
        # Check for duplicates and append number if needed
        counter = 1
        while CommunityUser.objects.filter(username=self.username).exclude(pk=self.pk).exists():
            self.username = f"{base_username}{counter}"
            counter += 1
                
        # Calculate age from date of birth if provided
        if self.date_of_birth:
            today = datetime.date.today()
            self.age = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        self.first_name = self.first_name.strip().capitalize()
        self.last_name = self.last_name.strip().capitalize()
        self.preferred_name = self.preferred_name.strip().capitalize() if self.preferred_name else None
        # First save to get the UUID if this is a new instance
        super().save(*args, **kwargs)
        # Generate member ID after we have the UUID
        if needs_member_id:
            # Generate member ID using the now-available UUID
            name_slug = slugify(
                f"{self.first_name[:MAX_MEMBER_ID_FIRST_NAME]}{self.last_name[:MAX_MEMBER_ID_LAST_NAME]}"
            ).upper()
            
            # Use current year if uploaded_at is not set
            year = self.user_uploaded_at.year if self.user_uploaded_at else datetime.datetime.now().year
            
            # Generate unique member ID E.g. 2025-ROME-SALARDAbDASDS3S
            uuid_part = str(self.id).replace('-', '')[:MAX_MEMBER_ID_LENGTH - len(name_slug) - 5]
            self.member_id = f"{year}-{name_slug}-{uuid_part}"
            
            # Save again to persist the member_id
            super().save(update_fields=['member_id'])
        
    def get_full_name(self):
        """Return first + last name, or preferred name if available"""
        if self.preferred_name:
            return self.preferred_name
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.preferred_name or self.first_name
    
    def is_guest(self):
        '''
        is the user an adult/youth guest or a volunteer
        '''
        return (
            self.ministry == CommunityUser.MinistryType.YOUTH_GUEST or 
            self.ministry == CommunityUser.MinistryType.ADULT_GUEST or
            self.ministry == CommunityUser.MinistryType.VOLUNTEER
            )

    def __str__(self):
        return f"{self.member_id} - {self.get_full_name()}"

class CommunityRole(models.Model):
    '''
    Role in the community
    '''
    class RoleType(models.TextChoices):
        MEMBER = "MEM", _("Member")
        NATIONAL_HEAD = "NAT_HEAD", _("National Head")
        YCOM_NATIONAL_HEAD = "YCOM_NAT_HEAD", _("YCOM National Head")
        MUSIC_MIN_NATIONAL_HEAD = "MUSIC_NAT_HEAD", _("Music Ministry National Head")
        CLUSTER_YOUTH_HEAD = "CLUSTER_HEAD", _("Cluster Head")
        AREA_YOUTH_HEAD = "AREA_HEAD", _("Area Head")
        CHAPTER_YOUTH_HEAD = "CHAPTER_HEAD", _("Chapter Head")
        HOUSEHOLD_YOUTH_HEAD = "HOUSEHOLD_HEAD", _("Household Head")
        SUPPORTING_HOUSEHOLD_HEAD = "SUPPORT_HH_HEAD", _("Supporting Household Head")
        SECTOR_YOUTH_HEAD = "SECTOR_HEAD", _("Sector Head")
        VOLUNTEER = "VOLUNTEER", _("Volunteer")
        GUEST = "GUEST", _("Guest")
        # non-visible auth fields - generally for frontend use and is less powerful than superuser, superuser and staff refer to backend access to api control
        
        EVENT_APPROVER = "EVENT_APPROVER", _("Event Approver") # just able to approve events
        EVENT_CREATOR = "EVENT_CREATOR", _("Event Creator") # able to create/edit/delete own events created
        
        COMMUNITY_ADMIN = "COMMUNITY_ADMIN", _("Community Admin") # able to promote other users to event approver status, higher level status than most
    
    role_name = models.CharField(
        max_length=20,  # FIXED: Added max_length
        choices=RoleType.choices,  # FIXED: Added .choices
        default=RoleType.MEMBER,
        verbose_name=_("role name"),
        unique=True
    )
    
    role_description = models.TextField(
        max_length=500,
        verbose_name=_("role description"),
        blank=True, 
        null=True
    )
    is_core = models.BooleanField(
        default=False, 
        verbose_name=_("is core role"),
        help_text=_("Defines if the role is a core role")
    )
    authority_level = models.IntegerField(verbose_name=_("community authority"), help_text=_("helper field to determine logical ranking of roles if many are assigned (max is 10)"), default=0, 
                                          validators=[MinValueValidator(0), MaxValueValidator(10)]
                                          )
    visible_role = models.BooleanField(verbose_name=_("defines if this is a public role to see"), default=True)
    
    class Meta:
        verbose_name = _("community role")
        verbose_name_plural = _("community roles")
        ordering = ["authority_level", "role_name"]
    
    def __str__(self):
        return self.get_role_name_display()

class UserCommunityRole(models.Model):
    '''
    Through model linking users to community roles with additional context
    '''
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="role_links",
        verbose_name=_("user")
    )
    
    role = models.ForeignKey(
        "CommunityRole", 
        on_delete=models.CASCADE, 
        related_name="user_links",
        verbose_name=_("role")
    )
    
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("assigned at")
    )
    
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="assigned_roles",
        verbose_name=_("assigned by")
    ) 
    
    # Additional fields for role context
    start_date = models.DateField(
        verbose_name=_("start date"),
        default=datetime.date.today
    )
    
    end_date = models.DateField(
        verbose_name=_("end date"),
        blank=True,
        null=True
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("active")
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("notes"),
        help_text=_("Additional information about this role assignment")
    )
    
    allowed_organisation_control = models.ManyToManyField(
        "events.Organisation", 
        blank=True, 
        help_text=_(
            "defines what organisations this user has permissions or control to")
        ) # used for encoders and what organisations they can create events for
    
    class Meta:
        unique_together = ("user", "role")
        verbose_name = _("user community role")
        verbose_name_plural = _("user community roles")
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.user} → {self.role} (by {self.assigned_by or 'system'})"
    
