# admin_users.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CommunityUser, CommunityRole,
    UserCommunityRole, Alergies, 
    EmergencyContact
    )

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
        # form.base_fields['date_of_birth'].widget.attrs['placeholder'] = 'YYYY-MM-DD'
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
    
@admin.register(Alergies)
class AlergiesAdmin(admin.ModelAdmin):
    list_display = ('alergy_name', 'alergy_description_preview')
    search_fields = ('alergy_name', 'alergy_description')
    list_per_page = 20
    
    fieldsets = (
        (None, {
            'fields': ('alergy_name', 'alergy_description')
        }),
    )
    
    def alergy_description_preview(self, obj):
        if obj.alergy_description:
            return obj.alergy_description[:100] + '...' if len(obj.alergy_description) > 100 else obj.alergy_description
        return "No description"
    alergy_description_preview.short_description = _('Description Preview')

class AlergiesInline(admin.TabularInline):
    model = Alergies
    extra = 1
    fields = ('alergy_name', 'alergy_description')
    verbose_name = _('Allergy')
    verbose_name_plural = _('Allergies')

@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = (
        'get_full_name', 'contact_relationship_display', 
        'phone_number', 'email', 'preferred_name_display'
    )
    list_filter = ('contact_relationship',)
    search_fields = (
        'first_name', 'last_name', 'preferred_name', 
        'email', 'phone_number'
    )
    list_per_page = 20
    
    fieldsets = (
        (_('Personal Information'), {
            'fields': (
                'first_name', 'last_name', 'middle_name', 'preferred_name'
            )
        }),
        (_('Contact Information'), {
            'fields': ('email', 'phone_number')
        }),
        (_('Relationship'), {
            'fields': ('contact_relationship',)
        }),
    )
    
    def get_full_name(self, obj):
        names = []
        if obj.first_name:
            names.append(obj.first_name)
        if obj.middle_name:
            names.append(obj.middle_name)
        if obj.last_name:
            names.append(obj.last_name)
        return " ".join(names) or "Unknown"
    get_full_name.short_description = _('Full Name')
    
    def contact_relationship_display(self, obj):
        return obj.get_contact_relationship_display() if obj.contact_relationship else "Not specified"
    contact_relationship_display.short_description = _('Relationship')
    
    def preferred_name_display(self, obj):
        return obj.preferred_name if obj.preferred_name else "—"
    preferred_name_display.short_description = _('Preferred Name')
    
    def get_queryset(self, request):
        return super().get_queryset(request)

class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 1
    fields = ('first_name', 'last_name', 'phone_number', 'contact_relationship')
    verbose_name = _('Emergency Contact')
    verbose_name_plural = _('Emergency Contacts')
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Make the relationship field optional in the inline
        formset.form.base_fields['contact_relationship'].required = False
        return formset