from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

import datetime
import uuid

from .metadata_models import Alergies, EmergencyContact

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, password=None, **extra_fields):
        if not extra_fields.get("first_name") or not extra_fields.get("last_name"):
            raise ValueError("Users must have a first and last name")
        
        # Generate username if not provided
        if not username:
            ministry = extra_fields.get("ministry", "CFC")
            first_name = extra_fields.get("first_name", "")
            last_name = extra_fields.get("last_name", "")
            username = slugify(f"{ministry}-{first_name}{last_name}").upper()
            
        email = extra_fields.get("email")
        user = self.model(
            username=username,
            email=self.normalize_email(email) if email else None,
            **extra_fields
        )        
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_encoder", True)
        return self.create_user(username, password, **extra_fields)

MAX_MEMBER_ID_LENGTH = 20
MAX_MEMBER_ID_FIRST_NAME = 5
MAX_MEMBER_ID_LAST_NAME = 5

class CommunityUser(AbstractBaseUser, PermissionsMixin):
    '''
    Main Auth Class for this project
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    member_id = models.CharField(
        max_length=100, 
        unique=True, 
        editable=False,
        verbose_name=_("member ID")
    )

    username = models.CharField(
        max_length=100, 
        unique=True,
        verbose_name=_("username")
    )

    class MinistryType(models.TextChoices):
        YFC = "YFC", _("Youth for Christ")
        CFC = "CFC", _("Couples for Christ")
        SFC = "SFC", _("Singles for Christ")
        KFC = "KFC", _("Kids for Christ")
        GUEST = "GST", _("Guest") 
        VOLUNTEER = "VLN", _("Volunteer")
        
    class GenderType(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")

    ministry = models.CharField(
        max_length=3, 
        choices=MinistryType.choices,  
        default=MinistryType.CFC,
        verbose_name=_("ministry")
    )
    
    email = models.EmailField(
        unique=True, 
        blank=True, 
        null=True,
        verbose_name=_("email address")
    )
    
    phone_number = models.CharField( 
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name=_("phone number")
    )
    
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
    
    gender = models.CharField(
        max_length=6, 
        choices=GenderType.choices,  # FIXED: Added .choices
        verbose_name=_("gender")
    )
    
    age = models.IntegerField(
        blank=True, 
        null=True, 
        validators=[MinValueValidator(0), MaxValueValidator(150)],
        verbose_name=_("age")
    )
    
    date_of_birth = models.DateField(
        verbose_name=_("date of birth"), 
        blank=True, 
        null=True,  # CHANGED: Removed default value for DOB
        help_text=_("Format: YYYY-MM-DD")
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("active")
    )
    
    is_staff = models.BooleanField(
        default=False,
        verbose_name=_("staff status")
    )
    
    is_encoder = models.BooleanField(
        default=False,
        verbose_name=_("encoder status")
    )
    
    # other information

    profile_picture = models.ImageField(
        upload_to="profile-images/", 
        blank=True, 
        null=True,
        verbose_name=_("profile picture")
    )
    
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("uploaded at")
    )
    
    alergies = models.ManyToManyField(
        Alergies, 
        verbose_name=_("Individual alergies"),
        related_name="users", 
        blank=True, 
        )
    
    emergency_contacts = models.ManyToManyField(
        EmergencyContact,
        verbose_name=_("Emergency contacts"),
        related_name="user_emergency_contacts",
        blank=True
    )
    
    # service information
    
    community_roles = models.ManyToManyField(
        "CommunityRole",         
        through="UserCommunityRole",
        through_fields=("user", "role"),
        related_name="users", 
        help_text=_("role/s in the community"), 
        blank=True
    )
    
    

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name", "gender"]
    
    class Meta:
        verbose_name = _("community user")
        verbose_name_plural = _("community users")
        # REMOVED: unique_together for first_name/last_name as it's too restrictive
        ordering = ["last_name", "first_name"]

    def save(self, *args, **kwargs):
        if not self.member_id:
            # Generate member ID
            name_slug = slugify(
                f"{self.first_name[:MAX_MEMBER_ID_FIRST_NAME]}{self.last_name[:MAX_MEMBER_ID_LAST_NAME]}"
            ).upper()
            
            # Use current year if uploaded_at is not set
            year = self.uploaded_at.year if self.uploaded_at else datetime.datetime.now().year
            
            # Generate unique member ID
            self.member_id = f"{year}-{name_slug}{str(self.id)[:MAX_MEMBER_ID_LENGTH - len(name_slug) - 5]}"
            
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
        if self.date_of_birth and not self.age:
            today = datetime.date.today()
            self.age = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
            
        super().save(*args, **kwargs)
        
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_short_name(self):
        return self.preferred_name or self.first_name

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
    
    role_name = models.CharField(
        max_length=20,  # FIXED: Added max_length
        choices=RoleType.choices,  # FIXED: Added .choices
        default=RoleType.MEMBER,
        verbose_name=_("role name")
    )
    
    role_description = models.TextField(
        max_length=500,
        verbose_name=_("role description")
    )
    
    is_core = models.BooleanField(
        default=False, 
        verbose_name=_("is core role"),
        help_text=_("Defines if the role is a core role")
    )
    
    class Meta:
        verbose_name = _("community role")
        verbose_name_plural = _("community roles")
        ordering = ["role_name"]
    
    def __str__(self):
        return self.get_role_name_display()

class UserCommunityRole(models.Model):
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
    
    class Meta:
        unique_together = ("user", "role")
        verbose_name = _("user community role")
        verbose_name_plural = _("user community roles")
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.user} → {self.role} (by {self.assigned_by or 'system'})"
    
