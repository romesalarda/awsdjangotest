from rest_framework import viewsets, filters, permissions
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.query import Q
from events.models import CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation
from events.api.serializers import *


class CountryLocationViewSet(viewsets.ModelViewSet):
    queryset = CountryLocation.objects.all().prefetch_related('clusters')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['general_sector', 'specific_sector']
    search_fields = ['country__name']
    ordering_fields = ['country', 'general_sector']
    ordering = ['country']

    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.query_params.get('nested', '').lower() == 'true':
            return NestedCountryLocationSerializer
        return CountryLocationSerializer

class ClusterLocationViewSet(viewsets.ModelViewSet):
    queryset = ClusterLocation.objects.all().select_related('world_location').prefetch_related('chapters')
    serializer_class = ClusterLocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['world_location__country', 'world_location__general_sector']
    search_fields = ['cluster_id', 'world_location__country__name']
    ordering_fields = ['cluster_id', 'world_location__country']
    ordering = ['world_location__country', 'cluster_id']

    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.query_params.get('nested', '').lower() == 'true':
            return NestedClusterLocationSerializer
        return ClusterLocationSerializer

class ChapterLocationViewSet(viewsets.ModelViewSet):
    queryset = ChapterLocation.objects.all().select_related(
        'cluster__world_location'
    ).prefetch_related('units')
    serializer_class = ChapterLocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['cluster__world_location__country', 'cluster__cluster_id']
    search_fields = ['chapter_name', 'chapter_code', 'chapter_id']
    ordering_fields = ['chapter_name', 'chapter_code', 'cluster__cluster_id']
    ordering = ['cluster__cluster_id', 'chapter_name']

    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.query_params.get('nested', '').lower() == 'true':
            return NestedChapterLocationSerializer
        return ChapterLocationSerializer

class UnitLocationViewSet(viewsets.ModelViewSet):
    queryset = UnitLocation.objects.all().select_related(
        'chapter__cluster__world_location'
    ).prefetch_related('areas')
    serializer_class = UnitLocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['chapter__cluster__world_location__country', 'chapter__chapter_name']
    search_fields = ['unit_name', 'unit_id', 'chapter__chapter_name']
    ordering_fields = ['unit_name', 'chapter__chapter_name']
    ordering = ['chapter__chapter_name', 'unit_name']

    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.query_params.get('nested', '').lower() == 'true':
            return NestedUnitLocationSerializer
        return UnitLocationSerializer

class AreaLocationViewSet(viewsets.ModelViewSet):
    queryset = AreaLocation.objects.all().select_related(
        'unit__chapter__cluster__world_location'
    )
    serializer_class = AreaLocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'unit__chapter__cluster__world_location__country',
        'unit__chapter__chapter_name',
        'unit__unit_name',
    ]
    search_fields = ['area_name', 'area_code', 'area_id', 'general_address', 'relative_search_areas__name']
    ordering_fields = ['area_name', 'area_code', 'unit__unit_name']
    ordering = ['unit__unit_name', 'area_name']
    
class SearchAreaSupportLocationViewSet(viewsets.ModelViewSet):
    """
    API .
    """
    queryset = SearchAreaSupportLocation.objects.all().order_by("name")
    serializer_class = SearchAreaSupportLocationSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class EventVenueViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing events.
    """
    queryset = EventVenue.objects.all().order_by("name")
    serializer_class = EventVenueSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]