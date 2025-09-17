import django_filters
from apps.events.models import Event
from django.db.models import Q

class EventFilter(django_filters.FilterSet):
    '''
    Event filtering based on various fields and related models.
    '''
    event_type = django_filters.CharFilter(lookup_expr="exact")
    area_type = django_filters.CharFilter(lookup_expr="exact")
    location = django_filters.CharFilter(method='filter_location')

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
    
    class Meta:
        model = Event
        fields = [
            "event_type", "area_type", "name",
            "area_name", "area_code", "venue_name", "venue_postcode", "location"
        ]