from rest_framework import viewsets, filters, permissions, response, status
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.query import Q

from apps.events.models import CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation
from apps.events.api.serializers import *


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
    
    @action(detail=False, methods=['get'], url_name="from-location", url_path="from-location")
    def get_chapter_from_location(self, request):
        '''
        get chapter info based on a location query parameter
        1. Try to find AreaLocation with area_name matching the query
        2. If not found, try to find SearchAreaSupportLocation with name matching the query
        3. If not found, try to find EventVenue with name matching the query
        4. If found in any of the above, return the associated ChapterLocation
        5. If not found in any, return 404 not found
        '''
        location_query = request.query_params.get('location')
        if not location_query:
            return response.Response({"detail": "location query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Try AreaLocation
        area = AreaLocation.objects.select_related('unit__chapter').filter(
            area_name__icontains=location_query
        ).first()
        if area and area.unit and area.unit.chapter:
            serializer = ChapterLocationSerializer(area.unit.chapter)
            return response.Response(serializer.data)

        # Try SearchAreaSupportLocation
        support = SearchAreaSupportLocation.objects.select_related('relative_area__unit__chapter').filter(
            name__icontains=location_query
        ).first()
        if support and support.relative_area and support.relative_area.unit and support.relative_area.unit.chapter:
            serializer = ChapterLocationSerializer(support.relative_area.unit.chapter)
            return response.Response(serializer.data)

        # Try EventVenue
        venue = EventVenue.objects.select_related('general_area__unit__chapter').filter(
            name__icontains=location_query
        ).first()
        if venue and venue.general_area and venue.general_area.unit and venue.general_area.unit.chapter:
            serializer = ChapterLocationSerializer(venue.general_area.unit.chapter)
            return response.Response(serializer.data)

        return response.Response({"detail": "No chapter found for this location."}, status=status.HTTP_404_NOT_FOUND)

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