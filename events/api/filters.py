from rest_framework import filters
from django_filters.rest_framework import FilterSet, CharFilter, DateFilter, ChoiceFilter, NumberFilter
from events.models import YouthCamp

class YouthCampFilter(FilterSet):
    # Location-based filtering
    country = CharFilter(field_name='specific_area__unit__chapter__cluster__world_location__country', lookup_expr='iexact')
    cluster = CharFilter(field_name='specific_area__unit__chapter__cluster__cluster_id', lookup_expr='iexact')
    chapter = CharFilter(field_name='specific_area__unit__chapter__chapter_name', lookup_expr='icontains')
    unit = CharFilter(field_name='specific_area__unit__unit_name', lookup_expr='iexact')
    area = CharFilter(field_name='specific_area__area_name', lookup_expr='icontains')
    
    # Date range filtering
    start_date_after = DateFilter(field_name='start_date', lookup_expr='gte')
    start_date_before = DateFilter(field_name='start_date', lookup_expr='lte')
    end_date_after = DateFilter(field_name='end_date', lookup_expr='gte')
    end_date_before = DateFilter(field_name='end_date', lookup_expr='lte')
    
    # Status filtering (based on current date)
    status = ChoiceFilter(choices=[
        ('upcoming', 'Upcoming'),
        ('ongoing', 'Ongoing'),
        ('past', 'Past')
    ], method='filter_by_status')
    
    # Participant count filtering
    min_participants = NumberFilter(field_name='number_of_pax', lookup_expr='gte')
    max_participants = NumberFilter(field_name='number_of_pax', lookup_expr='lte')
    
    class Meta:
        model = YouthCamp
        fields = [
            'area_type', 'specific_area', 'supervising_chapter_youth_head',
            'supervising_chapter_CFC_coordinator', 'theme', 'name'
        ]
    
    def filter_by_status(self, queryset, name, value):
        from django.utils import timezone
        today = timezone.now().date()
        
        if value == 'upcoming':
            return queryset.filter(start_date__gt=today)
        elif value == 'ongoing':
            return queryset.filter(start_date__lte=today, end_date__gte=today)
        elif value == 'past':
            return queryset.filter(end_date__lt=today)
        return queryset