import django_filters
from apps.events.models import Event
from django.db.models import Q

class EventFilter(django_filters.FilterSet):
    '''
    Enhanced event filtering based on various fields and related models.
    '''
    event_type = django_filters.CharFilter(lookup_expr="exact")
    event_type__in = django_filters.CharFilter(method='filter_event_types')
    area_type = django_filters.CharFilter(lookup_expr="exact")
    location = django_filters.CharFilter(method='filter_location')
    
    # Enhanced search capabilities
    search = django_filters.CharFilter(method='filter_search')
    name = django_filters.CharFilter(lookup_expr="icontains")

    # deep relationship filters
    area_name = django_filters.CharFilter(
        field_name="areas_involved__area_name", lookup_expr="icontains"
    )
    chapter = django_filters.CharFilter(
        field_name="areas_involved__unit__chapter__chapter_name", lookup_expr="icontains"
    )
    # Filter by area code (from areas_involved)
    area_code = django_filters.CharFilter(
        field_name="areas_involved__area_code", lookup_expr="iexact"
    )
    # Filter by venue name (from venues)
    venue_name = django_filters.CharFilter(
        field_name="venues__name", lookup_expr="icontains"
    )
    # Filter by venue postcode (from venues)
    venue_postcode = django_filters.CharFilter(
        field_name="venues__postcode", lookup_expr="icontains"
    )
    
    def filter_location(self, queryset, name, value):
        return queryset.filter(
            Q(areas_involved__area_name__icontains=value) |
            Q(areas_involved__relative_search_areas__name__icontains=value) |
            Q(venues__name__icontains=value) |
            Q(venues__postcode__icontains=value) 
            # Q(area_type=Event.EventAreaType.NATIONAL, name__icontains=value)
        ).distinct()
    
    def filter_event_types(self, queryset, name, value):
        """Filter by multiple event types separated by comma"""
        event_types = [event_type.strip() for event_type in value.split(',')]
        return queryset.filter(event_type__in=event_types)
    
    def filter_search(self, queryset, name, value):
        """Enhanced search across multiple event fields"""
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(sentence_description__icontains=value) |
            Q(theme__icontains=value) |
            Q(areas_involved__area_name__icontains=value) |
            Q(venues__name__icontains=value) |
            Q(venues__postcode__icontains=value)
        ).distinct()
    
    class Meta:
        model = Event
        fields = [
            "event_type", "event_type__in", "area_type", "name", "search",
            "area_name", "area_code", "venue_name", "venue_postcode", "location"
        ]