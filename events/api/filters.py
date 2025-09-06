import django_filters
from events.models import Event

class EventFilter(django_filters.FilterSet):
    # direct FK filters
    event_type = django_filters.CharFilter(lookup_expr="exact")
    area_type = django_filters.CharFilter(lookup_expr="exact")

    # deep relationship filters
    area = django_filters.CharFilter(field_name="specific_area__area_name")
    unit = django_filters.CharFilter(field_name="specific_area__unit__unit_name", lookup_expr="iexact")
    chapter = django_filters.CharFilter(field_name="specific_area__unit__chapter__chapter_name", lookup_expr="iexact")
    cluster = django_filters.CharFilter(field_name="specific_area__unit__chapter__cluster__cluster_id", lookup_expr="iexact")

    class Meta:
        model = Event
        fields = ["event_type", "area_type", "name", "unit", "chapter"]
