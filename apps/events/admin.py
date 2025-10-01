from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, 
    CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation,
    EventResource, EventVenue, SearchAreaSupportLocation,
    ExtraQuestion, QuestionChoice, QuestionAnswer,
    EventPaymentMethod, EventPaymentPackage, EventPayment, EventDayAttendance, ParticipantQuestion
)


# ! Location related admin

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
    
class YouthChapterHeadInline(admin.StackedInline):
    verbose_name = "Youth Chapter Head"
    verbose_name_plural = "Youth Chapter Heads"
    model = ChapterLocation.youth_chapter_heads.through
    extra = 1
    autocomplete_fields = ('communityuser',)
    
class AdultCoordinatorInline(admin.StackedInline):
    verbose_name = "Adult Coordinator"
    verbose_name_plural = "Adult Coordinators"
    model = ChapterLocation.adult_coordinators.through
    extra = 1
    autocomplete_fields = ('communityuser',)

@admin.register(ChapterLocation)
class ChapterLocationAdmin(admin.ModelAdmin):
    list_display = ('chapter_id', 'chapter_name', 'chapter_code', 'cluster')
    list_filter = ('cluster__world_location__country', 'cluster__world_location__general_sector')
    search_fields = ('chapter_name', 'chapter_code', 'chapter_id')
    ordering = ('cluster', 'chapter_name')
    autocomplete_fields = ('cluster',)
    readonly_fields = ('id', 'chapter_id')
    inlines = [YouthChapterHeadInline, AdultCoordinatorInline]
    
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
        
# ! Event related admin

@admin.register(EventRole)
class EventRoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'get_role_name_display', 'description')
    search_fields = ('role_name', 'description')
    ordering = ('role_name',)

class EventServiceTeamMemberInline(admin.StackedInline):
    model = EventServiceTeamMember
    extra = 1
    autocomplete_fields = ('user', 'assigned_by')
    # filter_horizontal = ('roles',)

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

class EventWorkshopInline(admin.StackedInline):
    model = EventWorkshop
    extra = 1
    autocomplete_fields = ('primary_facilitator',)
    filter_horizontal = ('facilitators',)
    fields = ('title', 'primary_facilitator', 'start_time', 'end_time', 'is_published')
    
class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 2  # number of blank choices to show
    ordering = ["order"]

@admin.register(ExtraQuestion)
class ExtraQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question_name", "event", "question_type", "required", "order")
    list_filter = ("event", "question_type", "required")
    search_fields = ("question_name", "question_body")
    ordering = ["event", "order"]
    inlines = [QuestionChoiceInline]
    
class ExtraQuestionInline(admin.StackedInline):
    model = ExtraQuestion
    extra = 0
    show_change_link = True
    ordering = ["order"]

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_code', 'event_type', 'end_date', 'number_of_pax', 'created_by')
    list_filter = ('event_type', 'area_type', 'start_date')
    search_fields = ('name', 'theme')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)
    readonly_fields = ('duration_days',)
    
    fieldsets = (
        (_('Basic Information'), {'fields': (
            'name', 'name_code', 'event_code', 'event_type', 'start_date', 'end_date', 'duration_days', 'created_by', 'status', 'approved', "payment_deadline"
        )}),
        (_('Location Information'), {'fields': (
            'area_type', 'areas_involved', 'venues'
        )}),
        (_('Event Details'), {'fields': (
            'description', 'sentence_description', 'theme', 'anchor_verse', 'number_of_pax', 'important_information', 
            'registration_deadline', 'what_to_bring'
        )}),
        (_('Supervision'), {'fields': (
            'supervising_youth_heads', 'supervising_CFC_coordinators'
        )}),
        (_('Resources'), {'fields': (
            'resources', 'memo', 'landing_image'
        )}),
        (_('Admin'), {'fields': (
            'notes', 'is_public', 'registration_open'
        )}),
    )
    
    inlines = [
        EventServiceTeamMemberInline,
        EventParticipantInline,
        EventTalkInline,
        EventWorkshopInline,
        ExtraQuestionInline
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
    
@admin.register(EventResource)
class PublicEventResourceAdmin(admin.ModelAdmin):
    list_display = (
        'resource_name', 'resource_link_preview', 'has_file', 
        'public_resource', 'created_at'
    )
    list_filter = ('public_resource', 'created_at')
    search_fields = ('resource_name', 'resource_link')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    # fieldsets = (
    #     (_('Resource Information'), {
    #         'fields': ('resource_name', 'resource_link', 'resource_file', 'public_resource')
    #     }),
    #     (_('Metadata'), {
    #         'fields': ('created_at',),
    #         'classes': ('collapse',)
    #     }),
    # )
    
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
    
class QuestionAnswerInline(admin.StackedInline):
    model = QuestionAnswer
    extra = 0
    show_change_link = True
    filter_horizontal = ("selected_choices",)  # nice UI for multi-select
    
@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'event', 'participant_type', 'status', 'registration_date')
    list_filter = ('participant_type', 'status', 'registration_date', 'event__event_type')
    search_fields = ('user__first_name', 'user__last_name', 'event__name')
    readonly_fields = ('id','registration_date', 'confirmation_date', 'attended_date')
    autocomplete_fields = ('user', 'event')
    date_hierarchy = 'registration_date'
    inlines = [QuestionAnswerInline]
    
@admin.register(SearchAreaSupportLocation)
class SearchAreaSupportLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "relative_area")
    search_fields = ("name", "relative_area__name")
    list_filter = ("relative_area",)


@admin.register(EventVenue)
class EventVenueAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "venue_type",
        "general_area",
        "max_allowed_people",
        "primary_venue",
    )
    search_fields = ("name", "postcode", "general_area__name")
    list_filter = ("venue_type", "primary_venue", "general_area")
    readonly_fields = ("id",)
    
# ! Payment 

@admin.register(EventPaymentMethod)
class EventPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("event", "method", "is_active", "created_at")
    list_filter = ("method", "is_active", "created_at")
    search_fields = ("event__name", "account_name", "account_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EventPaymentPackage)
class EventPaymentPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price_display", "currency", "capacity", "is_active")
    list_filter = ("currency", "is_active", "available_from", "available_until")
    search_fields = ("name", "event__name")
    readonly_fields = ("created_at", "updated_at")

    def price_display(self, obj):
        return f"{obj.price / 100:.2f} {obj.currency.upper()}"

    price_display.short_description = "Price"


@admin.register(EventPayment)
class EventPaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "package", "method", "amount_display", "status", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__id", "event__name", "stripe_payment_intent")
    readonly_fields = ("created_at", "updated_at")

    def amount_display(self, obj):
        return f"{obj.amount / 100:.2f} {obj.currency.upper()}"

    amount_display.short_description = "Amount"

class EventDayAttendanceInline(admin.TabularInline):
    model = EventDayAttendance
    extra = 1
    autocomplete_fields = ('user', 'event')
    readonly_fields = ('duration',)
    fields = ('user', 'event', 'day_date', 'day_id', 'check_in_time', 'check_out_time', 'duration')

@admin.register(EventDayAttendance)
class EventDayAttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'day_date', 'day_id', 'check_in_time', 'check_out_time', 'duration')
    list_filter = ('event', 'day_date')
    search_fields = ('user__first_name', 'user__last_name', 'event__name')
    autocomplete_fields = ('user', 'event')
    readonly_fields = ('duration',)
    ordering = ('-check_in_time',)
    
@admin.register(ParticipantQuestion)
class ParticipantQuestionAdmin(admin.ModelAdmin):
    list_display = ('question','participant', 'event', 'status', 'submitted_at', 'responded_at')
    