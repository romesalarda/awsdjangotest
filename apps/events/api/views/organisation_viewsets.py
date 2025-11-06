from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from apps.events.models import Organisation, OrganisationSocialMediaLink
from apps.events.api.serializers import (
    OrganisationSerializer,
    OrganisationListSerializer,
    OrganisationSocialMediaLinkSerializer,
)


class OrganisationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing organisations.
    
    Provides full CRUD operations for organisations with additional actions:
    - List all organisations with optional filtering
    - Create new organisations with nested social media links
    - Retrieve organisation details
    - Update organisation information
    - Delete organisations (admin only)
    - Manage social media links
    - Get organisation statistics
    
    Permissions:
    - Read operations: Authenticated or read-only
    - Create/Update/Delete: Admin users only
    
    Supported filters (query parameters):
    - search: Search in name and description
    - has_logo: Filter organisations with/without logo (true/false)
    - has_social_media: Filter organisations with social media links (true/false)
    """
    queryset = Organisation.objects.all().prefetch_related('social_media_links')
    serializer_class = OrganisationSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        Uses lightweight serializer for list view.
        """
        if self.action == 'list':
            return OrganisationListSerializer
        return OrganisationSerializer
    
    def get_permissions(self):
        """
        Set permissions based on action.
        - List and retrieve: Read-only or authenticated
        - Create, update, delete: Admin only
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticatedOrReadOnly()]
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        
        Supported filters:
        - search: Search in name and description
        - has_logo: Filter by logo presence (true/false)
        - has_social_media: Filter by social media link presence (true/false)
        """
        queryset = super().get_queryset()
        
        # Search filter
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        
        # Has logo filter
        has_logo = self.request.query_params.get('has_logo')
        if has_logo:
            if has_logo.lower() == 'true':
                queryset = queryset.exclude(logo='')
            elif has_logo.lower() == 'false':
                queryset = queryset.filter(logo='')
        
        # Has social media filter
        has_social_media = self.request.query_params.get('has_social_media')
        if has_social_media:
            if has_social_media.lower() == 'true':
                queryset = queryset.annotate(
                    social_count=Count('social_media_links')
                ).filter(social_count__gt=0)
            elif has_social_media.lower() == 'false':
                queryset = queryset.annotate(
                    social_count=Count('social_media_links')
                ).filter(social_count=0)
        
        return queryset
    
    @action(detail=True, methods=['get'], url_name='social-media', url_path='social-media')
    def social_media(self, request, pk=None):
        """
        Get all social media links for an organisation.
        
        Returns:
        - List of social media links
        - Count of links
        """
        organisation = self.get_object()
        social_links = organisation.social_media_links.all()
        
        serializer = OrganisationSocialMediaLinkSerializer(
            social_links, 
            many=True,
            context={'request': request}
        )
        
        return Response({
            "organisation_id": str(organisation.id),
            "organisation_name": organisation.name,
            "social_media_count": social_links.count(),
            "social_media_links": serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name='add-social-media', url_path='add-social-media', permission_classes=[permissions.IsAdminUser])
    def add_social_media(self, request, pk=None):
        """
        Add a new social media link to an organisation.
        
        Request body:
        {
            "name": "Twitter",
            "external_link": "https://twitter.com/org",
            "description": "Official Twitter account"
        }
        
        Returns:
        - Created social media link data
        """
        organisation = self.get_object()
        
        serializer = OrganisationSocialMediaLinkSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save(organisation=organisation)
            return Response({
                "status": "social media link added",
                "message": f"Social media link '{serializer.data['name']}' added to {organisation.name}",
                "social_media_link": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['delete'], url_name='remove-social-media', url_path='remove-social-media/(?P<link_id>[^/.]+)', permission_classes=[permissions.IsAdminUser])
    def remove_social_media(self, request, pk=None, link_id=None):
        """
        Remove a social media link from an organisation.
        
        URL parameter:
        - link_id: UUID of the social media link to remove
        
        Returns:
        - Success message
        """
        organisation = self.get_object()
        
        try:
            social_link = organisation.social_media_links.get(id=link_id)
            link_name = social_link.name
            social_link.delete()
            
            return Response({
                "status": "social media link removed",
                "message": f"Social media link '{link_name}' removed from {organisation.name}"
            }, status=status.HTTP_200_OK)
        except OrganisationSocialMediaLink.DoesNotExist:
            return Response({
                "error": "Social media link not found"
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'], url_name='statistics', url_path='statistics')
    def statistics(self, request):
        """
        Get organisation statistics.
        
        Returns:
        - Total organisations count
        - Organisations with logos
        - Organisations with social media
        - Average social media links per organisation
        """
        queryset = self.get_queryset()
        
        total_count = queryset.count()
        with_logo = queryset.exclude(logo='').count()
        
        # Annotate with social media count
        queryset_with_social = queryset.annotate(
            social_count=Count('social_media_links')
        )
        
        with_social_media = queryset_with_social.filter(social_count__gt=0).count()
        total_social_links = sum(
            org.social_count for org in queryset_with_social
        )
        avg_social_links = total_social_links / total_count if total_count > 0 else 0
        
        return Response({
            "total_organisations": total_count,
            "with_logo": with_logo,
            "with_social_media": with_social_media,
            "total_social_media_links": total_social_links,
            "average_social_links_per_org": round(avg_social_links, 2)
        }, status=status.HTTP_200_OK)


class OrganisationSocialMediaLinkViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing organisation social media links directly.
    
    Provides full CRUD operations for social media links:
    - List all social media links with filtering
    - Create new links
    - Retrieve link details
    - Update link information
    - Delete links (admin only)
    
    Permissions:
    - Read operations: Authenticated or read-only
    - Create/Update/Delete: Admin users only
    
    Supported filters (query parameters):
    - organisation: Filter by organisation ID
    - name: Filter by platform name (e.g., Facebook, Instagram)
    """
    queryset = OrganisationSocialMediaLink.objects.all().select_related('organisation')
    serializer_class = OrganisationSocialMediaLinkSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_permissions(self):
        """
        Set permissions based on action.
        - List and retrieve: Read-only or authenticated
        - Create, update, delete: Admin only
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticatedOrReadOnly()]
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        
        Supported filters:
        - organisation: Filter by organisation ID
        - name: Filter by platform name
        """
        queryset = super().get_queryset()
        
        # Filter by organisation
        organisation_id = self.request.query_params.get('organisation')
        if organisation_id:
            queryset = queryset.filter(organisation_id=organisation_id)
        
        # Filter by name/platform
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        return queryset
    
    @action(detail=False, methods=['get'], url_name='by-platform', url_path='by-platform/(?P<platform_name>[^/.]+)')
    def by_platform(self, request, platform_name=None):
        """
        Get all social media links for a specific platform.
        
        URL parameter:
        - platform_name: Name of the platform (e.g., Facebook, Instagram)
        
        Returns:
        - List of social media links for that platform
        - Count of links
        """
        links = self.get_queryset().filter(name__iexact=platform_name)
        
        serializer = self.get_serializer(links, many=True)
        
        return Response({
            "platform": platform_name,
            "count": links.count(),
            "links": serializer.data
        }, status=status.HTTP_200_OK)
