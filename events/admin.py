from django.contrib import admin
from .models import CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation, YouthCamp, YouthCampServiceTeamMember, YouthCampRole
from django.utils.html import format_html

@admin.register(CountryLocation)
class CountryLocationAdmin(admin.ModelAdmin):
    list_display = ('country', 'general_sector', 'specific_sector')
    list_filter = ('general_sector', 'specific_sector')
    search_fields = ('country__name',)
    ordering = ('country',)

@admin.register(ClusterLocation)
class ClusterLocationAdmin(admin.ModelAdmin):
    list_display = ('cluster_id', 'world_location')
    list_filter = ('world_location__general_sector', 'world_location__specific_sector')
    search_fields = ('cluster_id', 'world_location__country__name')
    ordering = ('world_location', 'cluster_id')
    autocomplete_fields = ('world_location',)

@admin.register(ChapterLocation)
class ChapterLocationAdmin(admin.ModelAdmin):
    list_display = ('chapter_id', 'chapter_name', 'chapter_code', 'cluster')
    list_filter = ('cluster__world_location__country', 'cluster__world_location__general_sector')
    search_fields = ('chapter_name', 'chapter_code', 'chapter_id')
    ordering = ('cluster', 'chapter_name')
    autocomplete_fields = ('cluster',)
    readonly_fields = ('id', 'chapter_id')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('cluster__world_location')

@admin.register(UnitLocation)
class UnitLocationAdmin(admin.ModelAdmin):
    list_display = ('unit_id', 'unit_name', 'chapter')
    list_filter = ('chapter__cluster__world_location__country',)
    search_fields = ('unit_name', 'unit_id', 'chapter__chapter_name')
    ordering = ('chapter', 'unit_name')
    autocomplete_fields = ('chapter',)
    readonly_fields = ('id', 'unit_id')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('chapter__cluster__world_location')

@admin.register(AreaLocation)
class AreaLocationAdmin(admin.ModelAdmin):
    list_display = ('area_id', 'area_name', 'area_code', 'unit', 'general_address')
    list_filter = ('unit__chapter__cluster__world_location__country',)
    search_fields = ('area_name', 'area_code', 'area_id', 'general_address')
    ordering = ('unit', 'area_name')
    autocomplete_fields = ('unit',)
    readonly_fields = ('id', 'area_id')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'unit__chapter__cluster__world_location'
        )

@admin.register(YouthCampRole)
class YouthCampRoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'get_role_name_display', 'description_short')
    list_filter = ('role_name',)
    search_fields = ('role_name', 'description')
    ordering = ('role_name',)
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if obj.description and len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'

@admin.register(YouthCampServiceTeamMember)
class YouthCampServiceTeamMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'youth_camp', 'roles_list', 'head_of_role', 'assigned_at', 'assigned_by')
    list_filter = ('youth_camp', 'head_of_role', 'roles', 'assigned_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'youth_camp__name')
    list_select_related = ('user', 'youth_camp', 'assigned_by')
    autocomplete_fields = ('user', 'youth_camp', 'assigned_by', 'roles')
    readonly_fields = ('assigned_at',)
    
    def roles_list(self, obj):
        return ", ".join([str(role) for role in obj.roles.all()])
    roles_list.short_description = 'Roles'

@admin.register(YouthCamp)
class YouthCampAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'venue_name', 'area_type', 'specific_area', 'service_team_count')
    list_filter = ('area_type', 'start_date', 'end_date', 'specific_area')
    search_fields = ('name', 'theme', 'venue_name', 'venue_address', 'anchor_verse')
    filter_horizontal = ('areas_involved',)
    autocomplete_fields = ('specific_area', 'supervising_chapter_youth_head', 'supervising_chapter_CFC_coordinator')
    readonly_fields = ('duration_days_display', 'service_team_list')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'start_date', 'end_date', 'theme', 'anchor_verse', 'number_of_pax')
        }),
        ('Location Information', {
            'fields': ('venue_name', 'venue_address', 'specific_area', 'area_type', 'areas_involved')
        }),
        ('Supervision', {
            'fields': ('supervising_chapter_youth_head', 'supervising_chapter_CFC_coordinator')
        }),
        ('Statistics', {
            'fields': ('duration_days_display', 'service_team_list'),
            'classes': ('collapse',)
        }),
    )
    
    def service_team_count(self, obj):
        return obj.service_team_members.count()
    service_team_count.short_description = 'Service Team Count'
    
    def duration_days_display(self, obj):
        return obj.duration_days
    duration_days_display.short_description = 'Duration (days)'
    
    def service_team_list(self, obj):
        members = obj.service_team_members.all().select_related('user')
        if not members:
            return "No service team members assigned"
        
        html = '<ul>'
        for member in members:
            roles = ", ".join([str(role) for role in member.roles.all()])
            html += f'<li>{member.user.get_full_name()} - {roles} {"(Head)" if member.head_of_role else ""}</li>'
        html += '</ul>'
        return format_html(html)
    service_team_list.short_description = 'Service Team Members'
    
    # Inline for service team members
    class YouthCampServiceTeamMemberInline(admin.TabularInline):
        model = YouthCampServiceTeamMember
        extra = 1
        autocomplete_fields = ('user', 'assigned_by', 'roles')
        readonly_fields = ('assigned_at',)
    
    def get_inlines(self, request, obj=None):
        if obj:  # Only show inline when editing an existing object
            return [self.YouthCampServiceTeamMemberInline]
        return []