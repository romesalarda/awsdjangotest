# admin_users.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import CommunityUser, CommunityRole, UserCommunityRole

@admin.register(CommunityRole)
class CommunityRoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'get_role_name_display', 'is_core')
    list_filter = ('is_core',)
    search_fields = ('role_name', 'role_description')
    ordering = ('role_name',)

class UserCommunityRoleInline(admin.TabularInline):
    model = UserCommunityRole
    extra = 1
    autocomplete_fields = ('user', 'role', 'assigned_by')
    fk_name = "user"

@admin.register(CommunityUser)
class CommunityUserAdmin(UserAdmin):
    list_display = ('member_id', 'username', 'get_full_name', 'ministry', 'gender', 'is_active', 'is_staff')
    list_filter = ('ministry', 'gender', 'is_active', 'is_staff', 'is_encoder')
    search_fields = ('member_id', 'username', 'first_name', 'last_name', 'email')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('member_id', 'username', 'uploaded_at')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal Info'), {'fields': (
            'member_id', 'first_name', 'last_name', 'middle_name', 
            'preferred_name', 'email', 'phone_number'
        )}),
        (_('Demographic Info'), {'fields': (
            'ministry', 'gender', 'date_of_birth', 'age'
        )}),
        (_('Permissions'), {'fields': (
            'is_active', 'is_staff', 'is_encoder', 'is_superuser',
            'groups', 'user_permissions'
        )}),
        (_('Profile'), {'fields': ('profile_picture',)}),
        (_('Important dates'), {'fields': ('uploaded_at', 'last_login')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'first_name', 'last_name', 'email', 'ministry', 'gender',
                'password1', 'password2'
            ),
        }),
    )
    
    inlines = [UserCommunityRoleInline]
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Make date_of_birth more user-friendly in admin
        form.base_fields['date_of_birth'].widget.attrs['placeholder'] = 'YYYY-MM-DD'
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