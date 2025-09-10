# admin_users.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CommunityUser, CommunityRole,
    UserCommunityRole, Allergy, 
    EmergencyContact, MedicalCondition, UserAllergy, UserMedicalCondition
    )

@admin.register(CommunityRole)
class CommunityRoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'get_role_name_display', 'is_core')
    list_filter = ('is_core',)
    search_fields = ('role_name', 'role_description')
    ordering = ('role_name',)

class UserCommunityRoleInline(admin.StackedInline):
    model = UserCommunityRole
    extra = 1
    autocomplete_fields = ('user', 'role', 'assigned_by')
    fk_name = "user"
    
class UserAllergyInline(admin.StackedInline):  # or admin.StackedInline
    model = UserAllergy
    extra = 1  # number of empty forms to display
    autocomplete_fields = ["allergy"]


class UserMedicalConditionInline(admin.StackedInline):
    model = UserMedicalCondition
    extra = 1
    autocomplete_fields = ["condition"]
    
class EmergencyContactInline(admin.StackedInline):  # or admin.StackedInline
    model = EmergencyContact
    extra = 1  # how many blank forms to show
    fields = (
        "first_name", "last_name", "middle_name", "preferred_name",
        "email", "phone_number", "secondary_phone",
        "contact_relationship", "address", "is_primary", "notes"
    )
    autocomplete_fields = ["user"]  # optional, usually not needed since inline sets user automatically


@admin.register(CommunityUser)
class CommunityUserAdmin(UserAdmin):
    list_display = (
        "member_id", "username", "get_full_name",
        "ministry", "gender", "is_active", "is_staff"
    )
    list_filter = ("ministry", "gender", "is_active", "is_staff", "is_encoder")
    search_fields = ("member_id", "username", "first_name", "last_name", "primary_email")
    ordering = ("last_name", "first_name")
    readonly_fields = ("member_id", "username", "user_uploaded_at", "profile_picture_uploaded_at")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal Info"), {"fields": (
            "member_id", "first_name", "last_name", "middle_name",
            "preferred_name", "primary_email", "secondary_email", "phone_number"
        )}),
        (_("Demographic Info"), {"fields": (
            "ministry", "gender", "date_of_birth", "age", "marital_status", "blood_type"
        )}),
        (_("Permissions"), {"fields": (
            "is_active", "is_staff", "is_encoder", "is_superuser",
            "groups", "user_permissions"
        )}),
        (_("Profile"), {"fields": ("profile_picture", "profile_picture_uploaded_at")}),
        (_("Important dates"), {"fields": ("user_uploaded_at", "last_login")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "first_name", "last_name", "primary_email",
                "ministry", "gender", "password1", "password2"
            ),
        }),
    )

    inlines = [UserCommunityRoleInline, UserAllergyInline, UserMedicalConditionInline, EmergencyContactInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form


@admin.register(UserCommunityRole)
class UserCommunityRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'assigned_at', 'is_active')
    list_filter = ('role', 'is_active', 'assigned_at')
    search_fields = ('user__first_name', 'user__last_name', 'role__role_name')
    autocomplete_fields = ('user', 'role', 'assigned_by')
    date_hierarchy = 'assigned_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'role', 'assigned_by')
    
@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("name", "description", "triggers")
    ordering = ("name",)


@admin.register(MedicalCondition)
class MedicalConditionAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("name", "description", "triggers")
    ordering = ("name",)


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "user", "contact_relationship", "phone_number", "is_primary")
    list_filter = ("contact_relationship", "is_primary")
    search_fields = ("first_name", "last_name", "email", "phone_number")
    ordering = ("last_name", "first_name")


@admin.register(UserAllergy)
class UserAllergyAdmin(admin.ModelAdmin):
    list_display = ("user", "allergy", "severity", "created_at", "updated_at")
    list_filter = ("severity", "created_at", "updated_at")
    search_fields = ("user__username", "allergy__name")
    ordering = ("user",)


@admin.register(UserMedicalCondition)
class UserMedicalConditionAdmin(admin.ModelAdmin):
    list_display = ("user", "condition", "severity", "date_diagnosed")
    list_filter = ("severity", "date_diagnosed")
    search_fields = ("user__username", "condition__name")
    ordering = ("user",)