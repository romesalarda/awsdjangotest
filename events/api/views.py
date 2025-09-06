from rest_framework import viewsets, filters, status
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, CharFilter, DateFilter, ChoiceFilter
from events.models import CountryLocation, ClusterLocation, ChapterLocation, UnitLocation, AreaLocation, YouthCamp, YouthCampServiceTeamMember, YouthCampRole
from.filters import YouthCampFilter
from .serialisers import *
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, Sum


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
        'unit__unit_name'
    ]
    search_fields = ['area_name', 'area_code', 'area_id', 'general_address']
    ordering_fields = ['area_name', 'area_code', 'unit__unit_name']
    ordering = ['unit__unit_name', 'area_name']
    
    
# youth camp viewsets

class YouthCampViewSet(viewsets.ModelViewSet):
    queryset = YouthCamp.objects.all().select_related(
        'specific_area',
        'supervising_chapter_youth_head',
        'supervising_chapter_CFC_coordinator'
    ).prefetch_related(
        'areas_involved',
        'service_team_members__user',
        'service_team_members__roles'
    )
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = YouthCampFilter  # Use custom filter class
    search_fields = ['name', 'theme', 'venue_name', 'venue_address', 'anchor_verse']
    ordering_fields = ['start_date', 'end_date', 'name', 'created_at', 'number_of_pax']
    ordering = ['-start_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DetailedYouthCampSerializer
        return YouthCampSerializer
    
    @action(detail=False, methods=['get'])
    def by_location(self, request):
        """
        Example: /api/youth-camps/by_location/?country=US&chapter=NewYork
        """
        filters = Q()
        
        # Country filter
        if country := request.query_params.get('country'):
            filters &= Q(specific_area__unit__chapter__cluster__world_location__country=country)
        
        # Cluster filter
        if cluster := request.query_params.get('cluster'):
            filters &= Q(specific_area__unit__chapter__cluster__cluster_id=cluster)
        
        # Chapter filter
        if chapter := request.query_params.get('chapter'):
            filters &= Q(specific_area__unit__chapter__chapter_name__icontains=chapter)
        
        # Unit filter
        if unit := request.query_params.get('unit'):
            filters &= Q(specific_area__unit__unit_name=unit)
        
        # Area filter
        if area := request.query_params.get('area'):
            filters &= Q(specific_area__area_name__icontains=area)
        
        camps = self.get_queryset().filter(filters)
        serializer = self.get_serializer(camps, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_date_range(self, request):
        """
        Query camps within a date range
        Example: /api/youth-camps/by_date_range/?start=2024-01-01&end=2024-12-31
        """
        start_date = request.query_params.get('start')
        end_date = request.query_params.get('end')
        
        if not start_date or not end_date:
            return Response(
                {'error': 'Both start and end date parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        camps = self.get_queryset().filter(
            start_date__gte=start_date,
            end_date__lte=end_date
        )
        serializer = self.get_serializer(camps, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get all upcoming camps"""
        from django.utils import timezone
        camps = self.get_queryset().filter(start_date__gt=timezone.now().date())
        serializer = self.get_serializer(camps, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def ongoing(self, request):
        """Get all ongoing camps"""
        from django.utils import timezone
        today = timezone.now().date()
        camps = self.get_queryset().filter(start_date__lte=today, end_date__gte=today)
        serializer = self.get_serializer(camps, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_supervisor(self, request):
        """Get camps by supervisor"""
        supervisor_id = request.query_params.get('supervisor_id')
        if not supervisor_id:
            return Response(
                {'error': 'supervisor_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        camps = self.get_queryset().filter(
            Q(supervising_chapter_youth_head_id=supervisor_id) |
            Q(supervising_chapter_CFC_coordinator_id=supervisor_id)
        )
        serializer = self.get_serializer(camps, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def service_team(self, request, pk=None):
        camp = self.get_object()
        members = camp.service_team_members.all().select_related('user', 'assigned_by').prefetch_related('roles')
        serializer = YouthCampServiceTeamMemberSerializer(members, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        camp = self.get_object()
        stats = {
            'total_service_team': camp.service_team_members.count(),
            'head_count': camp.service_team_members.filter(head_of_role=True).count(),
            'roles_distribution': {}
        }
        
        # Count members per role
        for member in camp.service_team_members.all():
            for role in member.roles.all():
                stats['roles_distribution'][role.role_name] = stats['roles_distribution'].get(role.role_name, 0) + 1
        
        return Response(stats)

class YouthCampServiceTeamMemberViewSet(viewsets.ModelViewSet):
    queryset = YouthCampServiceTeamMember.objects.all().select_related(
        'user', 'youth_camp', 'assigned_by'
    ).prefetch_related('roles')
    
    serializer_class = YouthCampServiceTeamMemberSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['youth_camp', 'user', 'head_of_role', 'roles']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'youth_camp__name']
    ordering_fields = ['assigned_at', 'user__last_name']
    ordering = ['-assigned_at']
    
    @action(detail=False, methods=['get'])
    def by_user(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({'error': 'user_id parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        memberships = self.get_queryset().filter(user_id=user_id)
        serializer = self.get_serializer(memberships, many=True)
        return Response(serializer.data)

class YouthCampRoleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = YouthCampRole.objects.all()
    serializer_class = YouthCampRoleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['role_name', 'description']
    ordering_fields = ['role_name']
    ordering = ['role_name']
    
    # ReadOnly because roles are predefined and shouldn't be modified via API