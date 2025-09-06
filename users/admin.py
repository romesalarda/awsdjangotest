from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CommunityUser, UserCommunityRole, CommunityRole

class UserCommunityThroughInLine(admin.TabularInline):
    model = UserCommunityRole
    extra = 1
    fk_name = "user"

@admin.register(CommunityUser)
class CustomUserAdmin(UserAdmin):
    model = CommunityUser

    # Show these fields in the list view
    list_display = ("member_id", "first_name", "last_name", "ministry", "email", "is_staff", "is_active", "gender", "age", "date_of_birth")
    list_filter = ("ministry", "is_staff", "is_active")

    # Read-only field (generated automatically)
    readonly_fields = ("member_id", "uploaded_at")

    # Fieldsets for viewing/editing users
    fieldsets = (
        (None, {"fields": ("member_id", "email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "middle_name", "preferred_name", "ministry", "gender", "age", "profile_picture")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "is_encoder", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "uploaded_at", "date_of_birth")}),
    )

    # Fields when creating a new user
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "ministry", "password1", "password2", "is_staff", "is_active")}
        ),
    )

    search_fields = ("member_id", "email", "first_name", "last_name")
    ordering = ("member_id",)
    inlines = [UserCommunityThroughInLine]

admin.site.register(UserCommunityRole)
admin.site.register(CommunityRole)