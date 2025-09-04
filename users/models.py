from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
import datetime

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, password=None, **extra_fields):
        if not extra_fields.get("first_name") or not extra_fields.get("last_name"):
            raise ValueError("Users must have a first and last name")
        email = extra_fields.get("email")
        user = self.model(
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

class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    member_id = models.CharField(max_length=100, unique=True, editable=False)

    username = models.CharField(max_length=100, unique=True)

    class MinistryType(models.TextChoices):
        YFC = "YFC", _("YOUTH_FOR_CHRIST")
        CFC = "CFC", _("COUPLES_FOR_CHRIST")
        SFC = "SFC", _("SINGLES_FOR_CHRIST")
        KFC = "KFC", _("KIDS_FOR_CHRIST")
        
    class GenderType(models.TextChoices):
        MALE = "MALE", _("MALE")
        FEMALE = "FEMALE", _("FEMALE")

    ministry = models.CharField(max_length=3, choices=MinistryType, default=MinistryType.CFC)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.IntegerField(blank=True, null=True)
    
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    preferred_name = models.CharField(max_length=50, blank=True, null=True)
    
    gender = models.CharField(max_length=6, choices=GenderType)
    age = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0), MaxValueValidator(150)])
    date_of_birth = models.DateField(verbose_name="DOB", blank=True, null=True, default=datetime.date.today)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_encoder = models.BooleanField(default=False)

    profile_picture = models.ImageField(upload_to="profile-images/", blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name"]
    
    class Meta:
        unique_together = ("first_name", "last_name")

    def save(self, *args, **kwargs):
        
        if not self.member_id:
            name_slug = slugify(f"{self.first_name[:MAX_MEMBER_ID_FIRST_NAME]}{self.last_name[:MAX_MEMBER_ID_LAST_NAME]}").upper()
            self.uploaded_at = datetime.date.today()
            self.member_id = f"{str(self.uploaded_at.year)}-{name_slug}{str(self.id)[:MAX_MEMBER_ID_LENGTH - len(name_slug) - 4]}"
            
        self.username = slugify(f"{self.ministry}-{self.first_name}{self.last_name}").upper()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.member_id
