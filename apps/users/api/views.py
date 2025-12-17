from rest_framework import filters, response, status
from rest_framework.decorators import action
from rest_framework import viewsets, permissions, views
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models
import threading

from .serializers import *
from apps.events.api.serializers import SimplifiedEventSerializer
from apps.events.models import Event
from apps.users.models import CommunityRole
from apps.users.email_utils import send_welcome_email

class CommunityUserViewSet(viewsets.ModelViewSet):
    '''
    Viewset related to user management
    '''
    queryset = get_user_model().objects.all()
    serializer_class = CommunityUserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ministry', 'gender', 'is_active', 'is_staff', 'is_encoder']
    search_fields = ['first_name', 'last_name', 'email', 'member_id', 'username']
    ordering_fields = ['last_name', 'first_name', 'date_of_birth', 'uploaded_at']
    ordering = ['last_name', 'first_name']
    permission_classes = [permissions.AllowAny] 
    lookup_field = "member_id"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    # TODO: double check read permissions - only logged in user can see the data about themselves and NO ONE else. Superusers can see everything - override Retrieve method
    
    def create(self, request, *args, **kwargs):
        """
        Override create to send welcome email after successful user registration.
        Also normalizes error responses for better frontend handling.
        """
        # Call parent create method
        try:
            response_data = super().create(request, *args, **kwargs)
        except Exception as e:
            # Normalize validation errors
            if hasattr(e, 'detail'):
                error_dict = {}
                if isinstance(e.detail, dict):
                    for field, errors in e.detail.items():
                        if isinstance(errors, list):
                            error_dict[field] = errors
                        else:
                            error_dict[field] = [str(errors)]
                else:
                    error_dict['general'] = [str(e.detail)]
                
                return response.Response({
                    'message': 'Registration failed. Please check the errors below.',
                    'errors': error_dict
                }, status=status.HTTP_400_BAD_REQUEST)
            raise e
        
        # Send welcome email in background thread to avoid blocking
        if response_data.status_code == status.HTTP_201_CREATED:
            try:
                # Get the newly created user
                user_id = response_data.data.get('id')
                if user_id:
                    User = get_user_model()
                    user = User.objects.get(id=user_id)
                    
                    # Send email in background
                    def send_email():
                        try:
                            send_welcome_email(user)
                            print(f"📧 Welcome email queued for user {user.username}")
                        except Exception as e:
                            print(f"⚠️ Failed to send welcome email: {e}")
                    
                    email_thread = threading.Thread(target=send_email)
                    email_thread.start()
            except Exception as e:
                # Don't fail the request if email fails
                print(f"⚠️ Error setting up welcome email: {e}")
        
        return response_data
        
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_name="self", url_path="me")
    def get_self(self, request):
        '''
        Get full user details about the current logged in user
        '''
        self.check_permissions(request)        
        serializer = CommunityUserSerializer(request.user)
        return response.Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_name="choices", url_path="choices")
    def get_choices(self, request):
        """
        Return selectable choices for profile fields to power dropdowns in the UI.
        """
        UserModel = get_user_model()

        def choices_to_list(choices):
            return [
                {"value": key, "label": label}
                for key, label in choices
            ]

        data = {
            "gender": choices_to_list(UserModel.GenderType.choices),
            "marital_status": choices_to_list(UserModel.MaritalType.choices),
            "blood_type": choices_to_list(UserModel.BloodType.choices),
            "ministry": choices_to_list(UserModel.MinistryType.choices),
        }
        return response.Response(data)
    
    @action(detail=False, methods=['patch'], permission_classes=[permissions.IsAuthenticated], url_name="update-profile", url_path="me/update")
    def update_profile(self, request):
        '''
        Update the current user's profile information
        Supports both JSON and multipart/form-data for file uploads
        '''
        self.check_permissions(request)
        serializer = ProfileUpdateSerializer(
            request.user, 
            data=request.data, 
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            updated_user = serializer.save()
            # Refresh from database to get the latest values
            updated_user.refresh_from_db()
            # Return the updated user data using the full serializer
            response_serializer = CommunityUserSerializer(updated_user)
            return response.Response({
                'message': 'Profile updated successfully',
                'user': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        # Normalize error response
        error_dict = {}
        for field, errors in serializer.errors.items():
            if field == 'errors' and isinstance(errors, dict):
                # If we have nested errors from validate(), flatten them
                error_dict.update(errors)
            else:
                # Convert error list to string
                if isinstance(errors, list):
                    error_dict[field] = errors[0] if errors else 'Invalid value'
                else:
                    error_dict[field] = str(errors)
        
        return response.Response({
            'message': 'Profile update failed',
            'errors': error_dict
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], 
            url_name="upload-picture", url_path="me/upload-picture",
            parser_classes=[MultiPartParser, FormParser])
    def upload_profile_picture(self, request):
        '''
        Upload or update the current user's profile picture
        Expects multipart/form-data with a 'profile_picture' file field
        '''
        self.check_permissions(request)
        
        if 'profile_picture' not in request.FILES:
            return response.Response({
                'message': 'No file provided',
                'errors': {'profile_picture': ['This field is required.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        profile_picture = request.FILES['profile_picture']
        
        # Validate file type
        allowed_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp']
        file_extension = profile_picture.name.split('.')[-1].lower()
        
        if file_extension not in allowed_extensions:
            return response.Response({
                'message': 'Invalid file type',
                'errors': {'profile_picture': [f'Only {", ".join(allowed_extensions)} files are allowed.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (max 5MB)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if profile_picture.size > max_size:
            return response.Response({
                'message': 'File too large',
                'errors': {'profile_picture': ['File size must not exceed 5MB.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the user's profile picture
        request.user.profile_picture = profile_picture
        request.user.save(update_fields=['profile_picture', 'profile_picture_uploaded_at'])
        
        # Return the updated user data
        response_serializer = CommunityUserSerializer(request.user)
        return response.Response({
            'message': 'Profile picture uploaded successfully',
            'user': response_serializer.data
        }, status=status.HTTP_200_OK)
    
    
    def get_serializer_class(self):
        # signed in users can only view full data about themselves
        print("get_serializer_class called for action:", self.action)
        if getattr(self, 'swagger_fake_view', False) and self.action == 'retrieve':
            return SimplifiedCommunityUserSerializer
        
        user = self.request.user
        if not user.is_authenticated:
            return SimplifiedCommunityUserSerializer

        if self.action in ['retrieve', 'update', 'partial_update']:
            obj = self.get_object()
            if obj == user or user.is_superuser:
                print("Returning full serializer for user:", user.username)
                return CommunityUserSerializer 
            print("Returning simplified serializer for user:", user.username)
            return SimplifiedCommunityUserSerializer
        return CommunityUserSerializer

    @action(detail=True, methods=['get'])
    def roles(self, request, member_id=None):
        '''
        Get all community roles assigned to this user, including organisation access.
        '''
        user = self.get_object()
        roles = user.role_links.all()
        serializer = UserCommunityRoleSerializer(roles, many=True)
        return response.Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='role-organisations')
    def get_role_organisations(self, request, member_id=None):
        '''
        Get all organisations this user has access to across all their roles.
        
        Returns a consolidated view of all organisations the user can manage/access
        based on their role assignments.
        
        GET /api/users/{member_id}/role-organisations/
        '''
        user = self.get_object()
        
        # Get all unique organisations across all user's roles
        from apps.events.models import Organisation
        organisation_ids = set()
        
        for role_link in user.role_links.filter(is_active=True):
            org_ids = role_link.allowed_organisation_control.values_list('id', flat=True)
            organisation_ids.update(org_ids)
        
        organisations = Organisation.objects.filter(id__in=organisation_ids)
        
        from apps.events.api.serializers import OrganisationSerializer
        serializer = OrganisationSerializer(organisations, many=True, context={'request': request})
        
        return response.Response({
            'count': len(organisation_ids),
            'organisations': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def events(self, request, member_id=None):
        user = self.get_object()
        now = timezone.now()

        # All events where the user is involved (service team OR participant)
        events = Event.objects.filter(
            models.Q(service_team_members__user=user) |
            models.Q(participants__user=user)
        ).distinct()

        # Split into upcoming and past
        upcoming_events = events.filter(start_date__gte=now).order_by('start_date')
        past_events = events.filter(start_date__lt=now).order_by('-start_date')

        serializer_upcoming = SimplifiedEventSerializer(upcoming_events, many=True)
        serializer_past = SimplifiedEventSerializer(past_events, many=True)

        # Add 'time_left' field to each upcoming event
        upcoming_events_data = serializer_upcoming.data
        for idx, event in enumerate(upcoming_events):
            start_date = event.start_date
            delta = start_date - now
            days = delta.days
            seconds = delta.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            # Format as 'X days, Y hours, Z minutes'
            time_left = f"{days} days, {hours} hours, {minutes} minutes" if days >= 0 else "Started"
            upcoming_events_data[idx]["time_left"] = time_left

        return response.Response({
            "upcoming_events": upcoming_events_data,
            "past_events": serializer_past.data
        })

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_name="search", url_path="search")
    def search_users(self, request):
        '''
        Search users by name, email, member_id, with location filtering
        For use in user selection dropdowns and autocomplete
        '''
        query = request.query_params.get('q', '').strip()
        area_id = request.query_params.get('area_id', None)
        ministry = request.query_params.get('ministry', None)
        limit = int(request.query_params.get('limit', 20))
        
        if not query:
            return response.Response([])
        
        queryset = get_user_model().objects.filter(is_active=True)
        
        # Text search across multiple fields
        queryset = queryset.filter(
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(preferred_name__icontains=query) |
            models.Q(primary_email__icontains=query) |
            models.Q(secondary_email__icontains=query) |
            models.Q(member_id__icontains=query) |
            models.Q(username__icontains=query)
        )
        
        # Optional filters
        if area_id:
            queryset = queryset.filter(area_from_id=area_id)
        
        if ministry:
            queryset = queryset.filter(ministry=ministry)
        
        # Order by relevance (exact matches first, then partial)
        queryset = queryset.order_by('last_name', 'first_name')[:limit]
        
        # Use simplified serializer for search results
        serializer = SimplifiedCommunityUserSerializer(queryset, many=True)
        return response.Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], 
            url_name="search-areas", url_path="search-areas")
    def search_areas(self, request):
        '''
        Search for area locations by area name, chapter name, or chapter code
        Returns areas with their chapter and cluster information
        Public endpoint - no authentication required for registration
        '''
        from apps.events.models import AreaLocation, ChapterLocation
        from apps.events.api.serializers import SimplifiedAreaLocationSerializer
        
        query = request.query_params.get('q', '').strip()
        chapter_filter = request.query_params.get('chapter', '').strip()
        limit = int(request.query_params.get('limit', 20))
        
        if not query and not chapter_filter:
            return response.Response({
                'message': 'Please provide a search query (q) or chapter filter',
                'areas': []
            })
        
        queryset = AreaLocation.objects.filter(active=True).select_related(
            'unit__chapter__cluster__world_location'
        )
        
        # Search by area name or chapter
        if query:
            queryset = queryset.filter(
                models.Q(area_name__icontains=query) |
                models.Q(unit__chapter__chapter_name__icontains=query) |
                models.Q(unit__chapter__chapter_code__icontains=query) |
                models.Q(area_code__icontains=query)
            )
        
        # Filter by specific chapter if provided
        if chapter_filter:
            queryset = queryset.filter(
                models.Q(unit__chapter__chapter_name__icontains=chapter_filter) |
                models.Q(unit__chapter__chapter_code__icontains=chapter_filter)
            )
        
        queryset = queryset.order_by('unit__chapter__chapter_name', 'area_name')[:limit]
        
        serializer = SimplifiedAreaLocationSerializer(queryset, many=True)
        return response.Response({
            'count': queryset.count(),
            'areas': serializer.data
        })
        
class CommunityRoleViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing community roles
    '''
    queryset = CommunityRole.objects.all()
    serializer_class = CommunityRoleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_core']
    search_fields = ['role_name', 'role_description']

class UserCommunityRoleViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing user-community roles with organisation control.
    
    Supports filtering by user, role, and active status.
    Includes actions for managing organisation access per role assignment.
    '''
    queryset = UserCommunityRole.objects.all().select_related('user', 'role').prefetch_related('allowed_organisation_control')
    serializer_class = UserCommunityRoleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['user', 'role', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'user__username', 'role__role_name']
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'], url_path='add-organisations')
    def add_organisations(self, request, pk=None):
        '''
        Add organisations to a user role's allowed_organisation_control.
        
        POST /api/user-community-roles/{id}/add-organisations/
        Body: {
            "organisation_ids": ["uuid1", "uuid2", ...]
        }
        '''
        user_role = self.get_object()
        organisation_ids = request.data.get('organisation_ids', [])
        
        if not organisation_ids:
            return response.Response({
                'message': 'No organisation IDs provided',
                'errors': {'organisation_ids': ['This field is required.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from apps.events.models import Organisation
        
        # Validate that all organisations exist
        organisations = Organisation.objects.filter(id__in=organisation_ids)
        if organisations.count() != len(organisation_ids):
            found_ids = set(str(org.id) for org in organisations)
            missing_ids = set(organisation_ids) - found_ids
            return response.Response({
                'message': 'Some organisations not found',
                'errors': {'organisation_ids': [f'Organisations not found: {", ".join(missing_ids)}']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Add organisations (won't create duplicates due to M2M relationship)
        user_role.allowed_organisation_control.add(*organisations)
        
        # Return updated role data
        serializer = self.get_serializer(user_role)
        return response.Response({
            'message': 'Organisations added successfully',
            'user_role': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='remove-organisations')
    def remove_organisations(self, request, pk=None):
        '''
        Remove organisations from a user role's allowed_organisation_control.
        
        POST /api/user-community-roles/{id}/remove-organisations/
        Body: {
            "organisation_ids": ["uuid1", "uuid2", ...]
        }
        '''
        user_role = self.get_object()
        organisation_ids = request.data.get('organisation_ids', [])
        
        if not organisation_ids:
            return response.Response({
                'message': 'No organisation IDs provided',
                'errors': {'organisation_ids': ['This field is required.']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from apps.events.models import Organisation
        
        # Get organisations to remove
        organisations = Organisation.objects.filter(id__in=organisation_ids)
        
        # Remove organisations
        user_role.allowed_organisation_control.remove(*organisations)
        
        # Return updated role data
        serializer = self.get_serializer(user_role)
        return response.Response({
            'message': 'Organisations removed successfully',
            'user_role': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='set-organisations')
    def set_organisations(self, request, pk=None):
        '''
        Set (replace) all organisations for a user role's allowed_organisation_control.
        
        POST /api/user-community-roles/{id}/set-organisations/
        Body: {
            "organisation_ids": ["uuid1", "uuid2", ...]
        }
        
        Empty array will clear all organisations.
        '''
        user_role = self.get_object()
        organisation_ids = request.data.get('organisation_ids', [])
        
        from apps.events.models import Organisation
        
        if organisation_ids:
            # Validate that all organisations exist
            organisations = Organisation.objects.filter(id__in=organisation_ids)
            if organisations.count() != len(organisation_ids):
                found_ids = set(str(org.id) for org in organisations)
                missing_ids = set(organisation_ids) - found_ids
                return response.Response({
                    'message': 'Some organisations not found',
                    'errors': {'organisation_ids': [f'Organisations not found: {", ".join(missing_ids)}']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set organisations (replaces existing)
            user_role.allowed_organisation_control.set(organisations)
        else:
            # Clear all organisations
            user_role.allowed_organisation_control.clear()
        
        # Return updated role data
        serializer = self.get_serializer(user_role)
        return response.Response({
            'message': 'Organisations updated successfully',
            'user_role': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], url_path='organisations')
    def get_organisations(self, request, pk=None):
        '''
        Get all organisations assigned to this user role.
        
        GET /api/user-community-roles/{id}/organisations/
        '''
        user_role = self.get_object()
        
        from apps.events.api.serializers import OrganisationSerializer
        organisations = user_role.allowed_organisation_control.all()
        serializer = OrganisationSerializer(organisations, many=True, context={'request': request})
        
        return response.Response({
            'count': organisations.count(),
            'organisations': serializer.data
        }, status=status.HTTP_200_OK)

class AlergiesViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing allergies
    '''
    queryset = Allergy.objects.all().order_by("name")
    serializer_class = AllergySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MedicalConditionsViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing medical conditions
    '''
    queryset = MedicalCondition.objects.all().order_by("name")
    serializer_class = MedicalConditionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class EmergencyContactViewSet(viewsets.ModelViewSet):
    '''
    Viewset for managing emergency contacts
    '''
    queryset = EmergencyContact.objects.all().select_related("user")
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]

class CurrentUserView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = CommunityUserSerializer(request.user)
        return response.Response(serializer.data)


class HealthCheckView(views.APIView):
    """
    Simple health check endpoint for container health monitoring.
    Returns 200 OK if Django is running.
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        return response.Response(
            {"status": "healthy", "service": "django", "secure": request.is_secure(), "scheme": request.scheme},
            status=status.HTTP_200_OK
        )