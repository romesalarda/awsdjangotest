from django.utils.text import slugify
from django.contrib.auth.models import BaseUserManager


class CommunityUserManager(BaseUserManager):
    '''
    Customer user manager for the community user model
    '''
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