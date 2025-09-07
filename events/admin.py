from django.contrib import admin
from django.utils.translation import gettext_lazy as _

import datetime
from .models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, 
    CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation,
    GuestParticipant, PublicEventResource,
    ExtraQuestion, QuestionChoice, QuestionAnswer
)

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

@admin.register(EventRole)
class EventRoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'get_role_name_display', 'description')
    search_fields = ('role_name', 'description')
    ordering = ('role_name',)

class EventServiceTeamMemberInline(admin.TabularInline):
    model = EventServiceTeamMember
    extra = 1
    autocomplete_fields = ('user', 'assigned_by')
    filter_horizontal = ('roles',)

class EventParticipantInline(admin.TabularInline):
    model = EventParticipant
    extra = 1
    autocomplete_fields = ('user',)
    readonly_fields = ('registration_date', 'confirmation_date', 'attended_date')
    fields = ('user', 'participant_type', 'status', 'registration_date')

class EventTalkInline(admin.TabularInline):
    model = EventTalk
    extra = 1
    autocomplete_fields = ('speaker',)
    fields = ('title', 'talk_type', 'speaker', 'start_time', 'end_time', 'is_published')

class EventWorkshopInline(admin.TabularInline):
    model = EventWorkshop
    extra = 1
    autocomplete_fields = ('primary_facilitator',)
    filter_horizontal = ('facilitators',)
    fields = ('title', 'primary_facilitator', 'start_time', 'end_time', 'is_published')
    
class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 2  # number of blank choices to show
    ordering = ["order"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_type', 'start_date', 'end_date', 'venue_name', 'number_of_pax')
    list_filter = ('event_type', 'area_type', 'start_date')
    search_fields = ('name', 'theme', 'venue_name', 'venue_address')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)
    readonly_fields = ('duration_days',)
    
    fieldsets = (
        (_('Basic Information'), {'fields': (
            'name', 'event_type', 'start_date', 'end_date', 'duration_days'
        )}),
        (_('Location Information'), {'fields': (
            'venue_name', 'venue_address', 'specific_area', 'area_type', 'areas_involved'
        )}),
        (_('Event Details'), {'fields': (
            'number_of_pax', 'theme', 'anchor_verse'
        )}),
        (_('Supervision'), {'fields': (
            'supervising_chapter_youth_head', 'supervising_chapter_CFC_coordinator'
        )}),
    )
    
    filter_horizontal = ('areas_involved',)
    autocomplete_fields = (
        'specific_area', 'supervising_chapter_youth_head', 
        'supervising_chapter_CFC_coordinator'
    )
    
    inlines = [
        EventServiceTeamMemberInline,
        EventParticipantInline,
        EventTalkInline,
        EventWorkshopInline
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'areas_involved', 'service_team'
        )

@admin.register(EventServiceTeamMember)
class EventServiceTeamMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'head_of_role', 'assigned_at')  
    list_filter = ('head_of_role', 'assigned_at', 'event__event_type')  
    search_fields = ('user__first_name', 'user__last_name', 'event__name')  
    autocomplete_fields = ('user', 'event', 'assigned_by')
    filter_horizontal = ('roles',)
    date_hierarchy = 'assigned_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'event', 'assigned_by') 
    


    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'event')

@admin.register(EventTalk)
class EventTalkAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'talk_type', 'speaker', 'start_time', 'is_published')
    list_filter = ('talk_type', 'is_published', 'start_time')
    search_fields = ('title', 'event__name', 'speaker__first_name', 'speaker__last_name')
    autocomplete_fields = ('event', 'speaker')
    date_hierarchy = 'start_time'
    ordering = ('-start_time',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('event', 'speaker')

@admin.register(EventWorkshop)
class EventWorkshopAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'primary_facilitator', 'start_time', 'is_published')
    list_filter = ('is_published', 'is_full', 'start_time')
    search_fields = ('title', 'event__name', 'primary_facilitator__first_name', 'primary_facilitator__last_name')
    autocomplete_fields = ('event', 'primary_facilitator')
    filter_horizontal = ('facilitators',)
    date_hierarchy = 'start_time'
    ordering = ('-start_time',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('event', 'primary_facilitator')
    
#! deprecated
# @admin.register(GuestParticipant)
# class GuestParticipantAdmin(admin.ModelAdmin):
#     list_display = (
#         'get_full_name', 'ministry_type_display', 'gender_display', 
#         'email', 'phone_number', 'outside_of_country'
#     )
#     list_filter = (
#         'ministry_type', 'gender', 'outside_of_country', 'date_of_birth',
#     )
#     search_fields = (
#         'first_name', 'last_name', 'email', 'phone_number', 
#         'preferred_name', 'country_of_origin__name'
#     )
#     filter_horizontal = ('chapter', 'alergies', 'emergency_contacts')
#     autocomplete_fields = ('country_of_origin',)
#     readonly_fields = ('age',)
#     date_hierarchy = 'date_of_birth'
    
#     fieldsets = (
#         (_('Personal Information'), {
#             'fields': (
#                 'first_name', 'last_name', 'middle_name', 'preferred_name',
#                 'gender', 'date_of_birth', 'age', 'profile_picture'
#             )
#         }),
#         (_('Contact Information'), {
#             'fields': ('email', 'phone_number')
#         }),
#         (_('Ministry Information'), {
#             'fields': ('ministry_type',)
#         }),
#         (_('Location Information'), {
#             'fields': ('chapter', 'outside_of_country', 'country_of_origin')
#         }),
#         (_('Health & Safety'), {
#             'fields': ('alergies', 'further_alergy_information', 'emergency_contacts'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def get_full_name(self, obj):
#         names = []
#         if obj.first_name:
#             names.append(obj.first_name)
#         if obj.last_name:
#             names.append(obj.last_name)
#         return " ".join(names) or "Unknown"
#     get_full_name.short_description = _('Full Name')
    
#     def ministry_type_display(self, obj):
#         return obj.get_ministry_type_display()
#     ministry_type_display.short_description = _('Ministry Type')
    
#     def gender_display(self, obj):
#         return obj.get_gender_display() if obj.gender else "Not specified"
#     gender_display.short_description = _('Gender')
    
#     def age(self, obj):
#         if obj.date_of_birth:
#             today = datetime.date.today()
#             return today.year - obj.date_of_birth.year - (
#                 (today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day)
#             )
#         return None
#     age.short_description = _('Age')
    
#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('country_of_origin').prefetch_related(
#             'chapter', 'alergies', 'emergency_contacts'
#         )

# class GuestParticipantInline(admin.TabularInline):
#     model = GuestParticipant
#     extra = 0
#     max_num = 10
#     fields = ('first_name', 'last_name', 'email', 'phone_number', 'ministry_type')
#     readonly_fields = ('first_name', 'last_name', 'email', 'phone_number', 'ministry_type')
#     can_delete = False
    
#     def has_add_permission(self, request, obj=None):
#         return False

@admin.register(PublicEventResource)
class PublicEventResourceAdmin(admin.ModelAdmin):
    list_display = (
        'resource_name', 'resource_link_preview', 'has_file', 
        'public_resource', 'created_at'
    )
    list_filter = ('public_resource', 'created_at')
    search_fields = ('resource_name', 'resource_link')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (_('Resource Information'), {
            'fields': ('resource_name', 'resource_link', 'resource_file', 'public_resource')
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def resource_link_preview(self, obj):
        if obj.resource_link:
            return obj.resource_link[:50] + '...' if len(obj.resource_link) > 50 else obj.resource_link
        return "No link"
    resource_link_preview.short_description = _('Resource Link Preview')
    
    def has_file(self, obj):
        return bool(obj.resource_file)
    has_file.boolean = True
    has_file.short_description = _('Has File')
    
    def save_model(self, request, obj, form, change):
        # Ensure only one of resource_link or resource_file is provided
        if obj.resource_link and obj.resource_file:
            pass
        super().save_model(request, obj, form, change)
        

@admin.register(ExtraQuestion)
class ExtraQuestionAdmin(admin.ModelAdmin):
    list_display = ("question_name", "event", "question_type", "required", "order")
    list_filter = ("event", "question_type", "required")
    search_fields = ("question_name", "question_body")
    ordering = ["event", "order"]
    inlines = [QuestionChoiceInline]
    
@admin.register(QuestionAnswer)
class QuestionAnswerAdmin(admin.ModelAdmin):
    list_display = ("participant", "question", "get_answer")
    list_filter = ("question__event", "question__question_type")
    search_fields = ("participant__user__username", "answer_text")

    def get_answer(self, obj):
        if obj.question.question_type in ["CHOICE", "MULTICHOICE"]:
            return ", ".join(c.text for c in obj.selected_choices.all())
        return obj.answer_text
    get_answer.short_description = "Answer"
    
class QuestionAnswerInline(admin.TabularInline):
    model = QuestionAnswer
    extra = 0
    show_change_link = True
    filter_horizontal = ("selected_choices",)  # nice UI for multi-select
    
@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'participant_type', 'status', 'registration_date')
    list_filter = ('participant_type', 'status', 'registration_date', 'event__event_type')
    search_fields = ('user__first_name', 'user__last_name', 'event__name')
    readonly_fields = ('registration_date', 'confirmation_date', 'attended_date')
    autocomplete_fields = ('user', 'event')
    date_hierarchy = 'registration_date'
    inlines = [QuestionAnswerInline]