import uuid
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from rest_framework import serializers
from django.conf import settings
from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email as django_validate_email
from difflib import SequenceMatcher
from datetime import date
import re

from apps.events.models import (
    Event, EventServiceTeamMember, EventRole, EventParticipant,
    EventTalk, EventWorkshop, EventPayment, EventDayAttendance
)
from apps.events.models.location_models import AreaLocation
from apps.users.models import EmergencyContact

from apps.events.api.serializers import *
from apps.events.api.serializers.event_serializers import ParticipantManagementSerializer
from apps.events.api.serializers.permission_serializers import (
    ServiceTeamPermissionSerializer, ServiceTeamPermissionUpdateSerializer
)
from apps.users.api.serializers import CommunityUserSerializer
from apps.events.api.filters import EventFilter
from apps.shop.api.serializers import EventProductSerializer, EventCartSerializer
from core.event_permissions import (
    has_full_event_access, can_manage_permissions, get_user_event_permissions,
    has_event_permission
)
from apps.shop.models import EventCart, ProductPayment, EventProduct, EventProductOrder, ProductSize
from apps.shop.api.serializers import EventCartMinimalSerializer
from apps.shop.api.serializers.payment_serializers import ProductPaymentMethodSerializer
from apps.events.websocket_utils import websocket_notifier, serialize_participant_for_websocket, get_event_supervisors
from apps.events.email_utils import send_booking_confirmation_email, send_payment_verification_email
from apps.shop.email_utils import send_payment_verified_email, send_order_update_email, send_cart_created_by_admin_email
import threading

#! Remember that service team members are also participants but not all participants are service team members

def test_safe_uuid(obj):
    try:
        obj = uuid.UUID(obj)
        return True
    except ValueError:
        return False

class EventViewSet(viewsets.ModelViewSet):
    '''
    Viewset for CRUD operations with all types of events in the community
    '''
    
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    lookup_field = 'id'  # Use UUID id field for lookups
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EventFilter
    # filterset_fields = ['event_type', 'area_type', 'specific_area', 'name']
    search_fields = ['name', 'theme']
    ordering_fields = ['start_date', 'end_date', 'name', 'number_of_pax']
    ordering = ['-start_date']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        # if params 'detailed' in request query params, return detailed serializer
        if self.action in ['list', 'retrieve']:
            detailed = self.request.query_params.get('detailed', 'false').lower() == 'true'
            if detailed:
                return EventSerializer
            else:
                return SimplifiedEventSerializer
        return super().get_serializer_class()
    
    def get_queryset(self):
        user = self.request.user
        print(f"🔧 DEBUG get_queryset - user: {user}, is_superuser: {user.is_superuser}, is_encoder: {getattr(user, 'is_encoder', False)}")
        
        # Base queryset - exclude DELETED events from all views (except Django admin)
        base_queryset = Event.objects.exclude(status=Event.EventStatus.DELETED)
        
        # For direct retrieval (detail view), allow access to COMPLETED events
        # For listing, exclude COMPLETED events from public discovery
        if self.action == 'retrieve':
            # Direct access: allow COMPLETED events to be viewed
            # This ensures event pages remain accessible after completion
            pass  # Use full base_queryset
        else:
            # Listing/discovery: exclude ARCHIEVED events from results
            # This prevents completed events from appearing in home/search/discovery
            base_queryset = base_queryset.exclude(Q(status=Event.EventStatus.ARCHIVED) & ~Q(created_by=user))
        
        if user.is_superuser:
            queryset = base_queryset
            print(f"🔧 DEBUG get_queryset - superuser queryset count: {queryset.count()}")
            return queryset
        
        if user.is_authenticated and user.is_encoder:
            # Encoder users can access events they created OR public events
            queryset = base_queryset.filter(
               Q(created_by=user) | Q(is_public=True)
            ).distinct()
            print(f"🔧 DEBUG get_queryset - encoder queryset count: {queryset.count()}")
            # print(f"🔧 DEBUG get_queryset - encoder queryset SQL: {queryset.query}")
            return queryset
        
        # For normal authenticated users, only show public events
        queryset = base_queryset.filter(is_public=True, approved=True)
        print(f"🔧 DEBUG get_queryset - regular user queryset count: {queryset.count()}")
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        user = request.user
        if user.is_authenticated:
            participant = EventParticipant.objects.filter(event=instance, user=user).first()
            data['is_participant'] = bool(participant)
            data['participant_count'] = EventParticipant.objects.filter(event=instance).count()

        return Response(data)
            
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        super().perform_create(serializer)
        
    @action(detail=True, methods=['get', 'post', 'delete'], url_name="service_team", url_path="service-team")
    def manage_service_team(self, request, id=None):
        '''
        Manage service team members for an event
        GET: List all service team members
        POST: Add a new service team member
        DELETE: Remove a service team member
        '''
        event = self.get_object()
        
        if request.method == 'GET':
            # TODO: add improved searchs in query
            # Return all service team members with their roles
            service_team = EventServiceTeamMember.objects.filter(event=event).select_related('user').prefetch_related('roles')
            serializer = EventServiceTeamMemberSerializer(service_team, many=True)
            return Response(serializer.data)
            
        elif request.method == 'POST':
            # Check permission to manage service team
            if not has_full_event_access(request.user, event):
                return Response(
                    {'error': 'You do not have permission to manage the service team'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Add new service team member
            user_id = request.data.get('user_id')
            role_ids = request.data.get('role_ids', [])
            head_of_role = request.data.get('head_of_role', False)
            permission_data = request.data.get('permissions', {})
            
            # Discount fields (optional)
            registration_discount_type = request.data.get('registration_discount_type')
            registration_discount_value = request.data.get('registration_discount_value')
            product_discount_type = request.data.get('product_discount_type')
            product_discount_value = request.data.get('product_discount_value')
            
            if not user_id:
                return Response(
                    {'error': 'user_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate discount values if provided
            if registration_discount_type and registration_discount_value is not None:
                try:
                    reg_discount_val = Decimal(str(registration_discount_value))
                    if reg_discount_val < 0:
                        return Response(
                            {'error': 'Registration discount value must be non-negative'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if registration_discount_type == 'PERCENTAGE' and reg_discount_val > 100:
                        return Response(
                            {'error': 'Registration discount percentage cannot exceed 100%'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except (ValueError, TypeError):
                    return Response(
                        {'error': 'Invalid registration discount value'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if product_discount_type and product_discount_value is not None:
                try:
                    prod_discount_val = Decimal(str(product_discount_value))
                    if prod_discount_val < 0:
                        return Response(
                            {'error': 'Product discount value must be non-negative'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if product_discount_type == 'PERCENTAGE' and prod_discount_val > 100:
                        return Response(
                            {'error': 'Product discount percentage cannot exceed 100%'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except (ValueError, TypeError):
                    return Response(
                        {'error': 'Invalid product discount value'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            try:
                user = get_user_model().objects.get(id=user_id)
                
                # Check if user is already in service team
                if EventServiceTeamMember.objects.filter(event=event, user=user).exists():
                    return Response(
                        {'error': 'User is already in the service team for this event'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Create service team member with discount fields
                service_member = EventServiceTeamMember.objects.create(
                    event=event,
                    user=user,
                    head_of_role=head_of_role,
                    assigned_by=request.user,
                    registration_discount_type=registration_discount_type,
                    registration_discount_value=registration_discount_value,
                    product_discount_type=product_discount_type,
                    product_discount_value=product_discount_value
                )                # Add roles if provided
                if role_ids:
                    roles = EventRole.objects.filter(id__in=role_ids)
                    service_member.roles.set(roles)
                
                # Create permissions if provided
                if permission_data:
                    from apps.events.models import ServiceTeamPermission
                    permission_data['service_team_member'] = service_member.id
                    permission_serializer = ServiceTeamPermissionSerializer(
                        data=permission_data,
                        context={'request': request}
                    )
                    if permission_serializer.is_valid():
                        permission_serializer.save()
                    else:
                        # Delete the service member if permission creation fails
                        service_member.delete()
                        return Response(
                            {'error': 'Invalid permission data', 'details': permission_serializer.errors}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    # Create default permissions (no access)
                    from apps.events.models import ServiceTeamPermission
                    ServiceTeamPermission.objects.create(
                        service_team_member=service_member,
                        role=ServiceTeamPermission.PermissionRole.CUSTOM,
                        granted_by=request.user
                    )
                
                # Refresh to get permissions
                service_member.refresh_from_db()
                serializer = EventServiceTeamMemberSerializer(service_member)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
                
            except get_user_model().DoesNotExist:
                return Response(
                    {'error': 'User not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {'error': str(e)}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        elif request.method == 'DELETE':
            # Check permission to manage service team
            if not has_full_event_access(request.user, event):
                return Response(
                    {'error': 'You do not have permission to manage the service team'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Remove service team member
            user_id = request.data.get('user_id')
            if not user_id:
                return Response(
                    {'error': 'user_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                service_member = EventServiceTeamMember.objects.get(event=event, user_id=user_id)
                service_member.delete()  # Permissions will be deleted via CASCADE
                return Response(
                    {'message': 'Service team member removed successfully'}, 
                    status=status.HTTP_200_OK
                )
            except EventServiceTeamMember.DoesNotExist:
                return Response(
                    {'error': 'Service team member not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

    @action(detail=True, methods=['patch'], url_name="update_service_member", url_path="service-team/(?P<member_id>[^/.]+)")
    def update_service_member(self, request, id=None, member_id=None):
        '''
        Update a specific service team member's roles, head_of_role status, permissions, or discounts
        '''
        event = self.get_object()
        
        # Check permission to manage service team or permissions
        if not has_full_event_access(request.user, event):
            return Response(
                {'error': 'You do not have permission to update service team members'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            service_member = EventServiceTeamMember.objects.get(event=event, id=member_id)
            
            # Validate discount fields if provided
            if 'registration_discount_type' in request.data or 'registration_discount_value' in request.data:
                reg_type = request.data.get('registration_discount_type', service_member.registration_discount_type)
                reg_value = request.data.get('registration_discount_value', service_member.registration_discount_value)
                
                if reg_type and reg_value is not None:
                    try:
                        reg_val = Decimal(str(reg_value))
                        if reg_val < 0:
                            return Response(
                                {'error': 'Registration discount value must be non-negative'}, 
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        if reg_type == 'PERCENTAGE' and reg_val > 100:
                            return Response(
                                {'error': 'Registration discount percentage cannot exceed 100%'}, 
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    except (ValueError, TypeError):
                        return Response(
                            {'error': 'Invalid registration discount value'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
            
            if 'product_discount_type' in request.data or 'product_discount_value' in request.data:
                prod_type = request.data.get('product_discount_type', service_member.product_discount_type)
                prod_value = request.data.get('product_discount_value', service_member.product_discount_value)
                
                if prod_type and prod_value is not None:
                    try:
                        prod_val = Decimal(str(prod_value))
                        if prod_val < 0:
                            return Response(
                                {'error': 'Product discount value must be non-negative'}, 
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        if prod_type == 'PERCENTAGE' and prod_val > 100:
                            return Response(
                                {'error': 'Product discount percentage cannot exceed 100%'}, 
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    except (ValueError, TypeError):
                        return Response(
                            {'error': 'Invalid product discount value'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
            
            # Update fields if provided
            if 'head_of_role' in request.data:
                service_member.head_of_role = request.data['head_of_role']
            
            # Update discount fields
            if 'registration_discount_type' in request.data:
                service_member.registration_discount_type = request.data['registration_discount_type']
            if 'registration_discount_value' in request.data:
                service_member.registration_discount_value = request.data['registration_discount_value']
            if 'product_discount_type' in request.data:
                service_member.product_discount_type = request.data['product_discount_type']
            if 'product_discount_value' in request.data:
                service_member.product_discount_value = request.data['product_discount_value']
            
            # Save updates
            service_member.save()
            
            if 'role_ids' in request.data:
                roles = EventRole.objects.filter(id__in=request.data['role_ids'])
                service_member.roles.set(roles)
            
            # Update permissions if provided
            if 'permissions' in request.data:
                permission_data = request.data['permissions']
                
                try:
                    # Try to get existing permissions
                    permissions = service_member.permissions
                    # Don't use partial=True for permissions - we need all fields to properly update booleans
                    # Frontend sends all permission fields, so this is safe
                    permission_serializer = ServiceTeamPermissionSerializer(
                        permissions,
                        data=permission_data,
                        partial=False,
                        context={'request': request}
                    )
                except:
                    # Create new permissions if they don't exist
                    from apps.events.models import ServiceTeamPermission
                    permission_data['service_team_member'] = service_member.id
                    permission_serializer = ServiceTeamPermissionSerializer(
                        data=permission_data,
                        context={'request': request}
                    )
                
                if permission_serializer.is_valid():
                    permission_serializer.save()
                else:
                    return Response(
                        {'error': 'Invalid permission data', 'details': permission_serializer.errors}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Refresh to get updated permissions
            service_member.refresh_from_db()
            serializer = EventServiceTeamMemberSerializer(service_member)
            return Response(serializer.data)
            
        except EventServiceTeamMember.DoesNotExist:
            return Response(
                {'error': 'Service team member not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'], url_name="roles", url_path="roles")
    def get_event_roles(self, request):
        '''
        Get all available event roles for selection
        '''
        roles = EventRole.objects.all().order_by('role_name')
        serializer = EventRoleSerializer(roles, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name="my_permissions", url_path="my-permissions")
    def get_my_permissions(self, request, id=None):
        '''
        Get the current user's permissions for this event
        '''
        event = self.get_object()
        permissions = get_user_event_permissions(request.user, event)
        print("permissions:", permissions)
        if permissions is None:
            return Response(
                {'error': 'You do not have access to this event'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response(permissions)
    
    @action(detail=True, methods=['get', 'patch'], url_name="member_permissions", url_path="service-team/(?P<member_id>[^/.]+)/permissions")
    def manage_member_permissions(self, request, id=None, member_id=None):
        '''
        GET: Get permissions for a specific service team member
        PATCH: Update permissions for a specific service team member
        '''
        event = self.get_object()
        
        # Check if user can manage permissions
        if not can_manage_permissions(request.user, event):
            return Response(
                {'error': 'You do not have permission to manage service team permissions'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            service_member = EventServiceTeamMember.objects.get(event=event, id=member_id)
            
            if request.method == 'GET':
                # Get current permissions
                try:
                    permissions = service_member.permissions
                    serializer = ServiceTeamPermissionSerializer(permissions)
                    return Response(serializer.data)
                except:
                    # No permissions set yet
                    return Response({
                        'role': 'CUSTOM',
                        'message': 'No permissions set for this service team member'
                    }, status=status.HTTP_200_OK)
            
            elif request.method == 'PATCH':
                # Update permissions
                try:
                    permissions = service_member.permissions
                    # Don't use partial=True for permissions - we need all fields to properly update booleans
                    # Frontend sends all permission fields, so this is safe
                    serializer = ServiceTeamPermissionSerializer(
                        permissions,
                        data=request.data,
                        partial=False,
                        context={'request': request}
                    )
                except:
                    # Create new permissions
                    from apps.events.models import ServiceTeamPermission
                    data = request.data.copy()
                    data['service_team_member'] = service_member.id
                    serializer = ServiceTeamPermissionSerializer(
                        data=data,
                        context={'request': request}
                    )
                
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                else:
                    return Response(
                        {'error': 'Invalid permission data', 'details': serializer.errors}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        except EventServiceTeamMember.DoesNotExist:
            return Response(
                {'error': 'Service team member not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'], url_name="my_discounts", url_path="my-discounts")
    def get_my_discounts(self, request, id=None):
        '''
        Get the current user's applicable discounts for this event.
        
        Discount Priority (cascading):
        1. EventServiceTeamMember discount (individual override)
        2. EventRoleDiscount (role-based for this event)
        3. Event.registration_discount (event-level default)
        
        Returns discount information for both registration and products.
        '''
        event = self.get_object()
        user = request.user
        
        if not user.is_authenticated:
            return Response(
                {'error': 'Authentication required'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        from apps.shop.models import ProductPaymentPackage
        from apps.events.models import EventRoleDiscount
        
        response_data = {
            'is_service_team': False,
            'registration_discount': None,
            'product_discount': None,
            'event_level_discount': None,
            'role_based_discount': None,
            'discount_source': None  # 'individual', 'role', 'event', or None
        }
        
        # Get original price from first payment package
        payment_packages = ProductPaymentPackage.objects.filter(event=event, is_active=True).order_by('price')
        original_price = Decimal(payment_packages.first().price) if payment_packages.exists() else Decimal('0.00')
        
        # Check for event-level discount (lowest priority)
        if event.has_registration_discount and original_price > 0:
            response_data['event_level_discount'] = {
                'type': event.registration_discount_type,
                'value': float(event.registration_discount_value),
                'original_price': float(original_price),
                'discounted_price': float(event.get_discounted_registration_price(original_price)),
                'savings': float(event.calculate_registration_discount(original_price))
            }
        
        # Check if user is a service team member
        try:
            service_member = EventServiceTeamMember.objects.prefetch_related('roles').get(event=event, user=user)
            response_data['is_service_team'] = True
            
            # Priority 1: Check for individual service team member discount (highest priority)
            if service_member.has_registration_discount and original_price > 0:
                response_data['registration_discount'] = {
                    'type': service_member.registration_discount_type,
                    'value': float(service_member.registration_discount_value),
                    'original_price': float(original_price),
                    'discounted_price': float(service_member.get_discounted_registration_price(original_price)),
                    'savings': float(service_member.calculate_registration_discount(original_price))
                }
                response_data['discount_source'] = 'individual'
            
            # Priority 2: Check for role-based discount (if no individual discount)
            if not response_data['registration_discount'] and service_member.roles.exists() and original_price > 0:
                # Get all roles for this service team member
                role_ids = service_member.roles.values_list('id', flat=True)
                
                # Find role discounts for this event (prioritize by discount value - highest first)
                role_discount = EventRoleDiscount.objects.filter(
                    event=event,
                    role__id__in=role_ids,
                    registration_discount_type__isnull=False,
                    registration_discount_value__gt=0
                ).order_by('-registration_discount_value').first()
                
                if role_discount:
                    response_data['role_based_discount'] = {
                        'type': role_discount.registration_discount_type,
                        'value': float(role_discount.registration_discount_value),
                        'original_price': float(original_price),
                        'discounted_price': float(role_discount.get_discounted_registration_price(original_price)),
                        'savings': float(role_discount.calculate_registration_discount(original_price)),
                        'role_name': role_discount.role.get_role_name_display()
                    }
                    response_data['registration_discount'] = response_data['role_based_discount']
                    response_data['discount_source'] = 'role'
            
            # Priority 3: Use event-level discount if no individual or role discount
            if not response_data['registration_discount'] and response_data['event_level_discount']:
                response_data['registration_discount'] = response_data['event_level_discount']
                response_data['discount_source'] = 'event'
            
            # Product discount details - check individual, then role-based
            if service_member.has_product_discount:
                response_data['product_discount'] = {
                    'type': service_member.product_discount_type,
                    'value': float(service_member.product_discount_value),
                    'description': f"{service_member.product_discount_value}{'%' if service_member.product_discount_type == 'PERCENTAGE' else '£'} off all products",
                    'source': 'individual'
                }
            elif service_member.roles.exists():
                # Check for role-based product discount
                role_ids = service_member.roles.values_list('id', flat=True)
                role_discount = EventRoleDiscount.objects.filter(
                    event=event,
                    role__id__in=role_ids,
                    product_discount_type__isnull=False,
                    product_discount_value__gt=0
                ).order_by('-product_discount_value').first()
                
                if role_discount:
                    response_data['product_discount'] = {
                        'type': role_discount.product_discount_type,
                        'value': float(role_discount.product_discount_value),
                        'description': f"{role_discount.product_discount_value}{'%' if role_discount.product_discount_type == 'PERCENTAGE' else '£'} off all products",
                        'source': 'role',
                        'role_name': role_discount.role.get_role_name_display()
                    }
            
        except EventServiceTeamMember.DoesNotExist:
            # Not a service team member, use event-level discount if available
            if response_data['event_level_discount']:
                response_data['registration_discount'] = response_data['event_level_discount']
                response_data['discount_source'] = 'event'
        
        return Response(response_data)

    @action(detail=True, methods=['get', 'post'], url_name="role_discounts", url_path="role-discounts")
    def role_discounts(self, request, id=None):
        '''
        Manage role-based discounts for this event.
        GET: List all role discounts for this event
        POST: Create or update role discounts for this event
        '''
        event = self.get_object()
        
        # Check permissions
        if not has_full_event_access(request.user, event):
            return Response(
                {'error': 'You do not have permission to manage role discounts for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.events.models import EventRoleDiscount
        from apps.events.api.serializers import EventRoleDiscountSerializer
        
        if request.method == 'GET':
            # Get all role discounts for this event
            role_discounts = EventRoleDiscount.objects.filter(event=event).select_related('role')
            serializer = EventRoleDiscountSerializer(role_discounts, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            # Create or update role discounts
            # Expected format: { discounts: [{ id, role_id, registration_discount_type, ... }, ...] }
            # If a role discount exists but is not in the list, it will be deleted
            role_discounts_data = request.data
            
            created = []
            updated = []
            deleted = []
            errors = []
            
            # Get all existing role discounts for this event
            existing_discounts = EventRoleDiscount.objects.filter(event=event)
            
            # Track which discount IDs are in the incoming data
            incoming_discount_ids = set()
            incoming_role_ids = set()
            
            for discount_data in role_discounts_data.get("discounts", []):
                try:
                    role_id = discount_data.get('role_id') or discount_data.get('role')
                    discount_id = discount_data.get('id')
                    
                    if not role_id:
                        errors.append({'error': 'role_id is required', 'data': discount_data})
                        continue
                    
                    incoming_role_ids.add(role_id)
                    
                    # If ID is provided, update existing
                    if discount_id:
                        incoming_discount_ids.add(discount_id)
                        try:
                            role_discount = EventRoleDiscount.objects.get(id=discount_id, event=event)
                            role_discount.role = get_object_or_404(EventRole, id=role_id)
                            role_discount.registration_discount_type = discount_data.get('registration_discount_type')
                            role_discount.registration_discount_value = discount_data.get('registration_discount_value', 0)
                            role_discount.product_discount_type = discount_data.get('product_discount_type')
                            role_discount.product_discount_value = discount_data.get('product_discount_value', 0)
                            role_discount.save()
                            updated.append(EventRoleDiscountSerializer(role_discount).data)
                        except EventRoleDiscount.DoesNotExist:
                            errors.append({'error': f'Role discount with id {discount_id} not found', 'data': discount_data})
                    else:
                        # Create new discount
                        role_discount = EventRoleDiscount.objects.create(
                            event=event,
                            role_id=role_id,
                            registration_discount_type=discount_data.get('registration_discount_type'),
                            registration_discount_value=discount_data.get('registration_discount_value', 0),
                            product_discount_type=discount_data.get('product_discount_type'),
                            product_discount_value=discount_data.get('product_discount_value', 0),
                        )
                        created.append(EventRoleDiscountSerializer(role_discount).data)
                        
                except Exception as e:
                    errors.append({'error': str(e), 'data': discount_data})
            
            # Delete role discounts that were not included in the incoming data
            discounts_to_delete = existing_discounts.exclude(role_id__in=incoming_role_ids)
            for discount in discounts_to_delete:
                deleted.append(EventRoleDiscountSerializer(discount).data)
                discount.delete()
            
            return Response({
                'created': created,
                'updated': updated,
                'deleted': deleted,
                'errors': errors
            }, status=status.HTTP_200_OK if not errors or (created or updated or deleted) else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'], url_name="delete_role_discount", url_path="role-discounts/(?P<discount_id>[^/.]+)")
    def delete_role_discount(self, request, id=None, discount_id=None):
        '''
        Delete a specific role discount for this event.
        '''
        event = self.get_object()
        
        # Check permissions
        if not has_full_event_access(request.user, event):
            return Response(
                {'error': 'You do not have permission to manage role discounts for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.events.models import EventRoleDiscount
        
        try:
            role_discount = EventRoleDiscount.objects.get(id=discount_id, event=event)
            role_discount.delete()
            return Response({'message': 'Role discount deleted successfully'}, status=status.HTTP_200_OK)
        except EventRoleDiscount.DoesNotExist:
            return Response({'error': 'Role discount not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'], url_name="booking", url_path="booking")
    def booking(self, request, id=None):
        '''
        Handle event booking logic here.
        '''
        # Manual booking details
        data = {           
            "event": {},
            "registration": {},
            "user": {},
            "merch": [],
            "resources": [],
            "questions": []
        }
        
        user = request.user
        if not user.is_authenticated:
            return Response(
                {'error': _('Authentication credentials were not provided.')},
                status=status.HTTP_401_UNAUTHORIZED
            )
        print("User:", user)
        self.check_object_permissions(request, self.get_object())
        self.check_permissions(request)
        # print("Permissions checked")
        #! handle event details first
        event = self.get_object()
        serializer = EventSerializer(event)
        event_data = serializer.data
        basic_info = event_data.pop("basic_info", {})
        basic_info.pop("auto_approve_participants", None)
        basic_info.pop("status", None)
        event_dates = event_data.pop("dates", [])
        event_venue = event_data.pop("venue", {})
        event_people = event_data.pop("people", {})
        event_data.pop("payment_packages")
        event_data.pop("payment_methods")
        payment_deadline = event_dates.get("payment_deadline", None)

        basic_info.update({
            "dates": event_dates,
            "locations": [
                {
                    "name": location.get("name", ""), 
                    "address": self.get_full_address(location),
                    "venue_type": location.get("venue_type", "")
                } 
                for location in event_venue.pop("venues", [])
                ],
            "areas_involved": [area['area_name'] for area in event_venue.get("areas_involved", [])],
            "organiser_info": event_people.get("organisers", []),
        })
        data['event'] = basic_info
        
        #! registration info
        event_participant = EventParticipant.objects.filter(event=event, user=user).first()
        if not event_participant:
            return Response(
                {'error': _('You are not registered for this event.')},
                status=status.HTTP_403_FORBIDDEN
            )
        participant_serializer = EventParticipantSerializer(event_participant)
        
        register_data = participant_serializer.data

        health_info = register_data.pop("health", {})
        medical_info = health_info.get("medical_conditions", [])
        allergies = health_info.get("allergies", [])
        
        event_payments = register_data.pop("event_payments", [])
        # get most recent payment
        payment_details = event_payments[0] if event_payments else {}
        payment_details.pop("user", None)
        payment_details.pop("event", None)
        payment_details.pop("event_name", None)
        payment_details.pop("participant_details", None)
        payment_details.pop("id", None)
        payment_details.pop("status", None)
        payment_details.pop("package", None)
        payment_details.pop("stripe_payment_intent", None)
        method_id = payment_details.pop("method", None)
        payment_details.pop("amount", None)
        payment_details.pop("participant_user_email", None)
                
        if method_id and not payment_details.get("verified", False):
            payment_details["method_info"] = EventPaymentMethod.objects.filter(id=method_id).values().first()
        else:
            payment_details["method_info"] = None
            
        payment_details["payment_deadline"] = payment_deadline

        question_answers = QuestionAnswer.objects.filter(participant=event_participant).prefetch_related("selected_choices")
        question_answer_serializer = QuestionAnswerSerializer(question_answers, many=True)
        answers_data = question_answer_serializer.data

        registration_data = {
            "confirmation_number": register_data.pop("event_user_id"),
            "status": register_data.pop("status", {}).get("code", "500 ERROR"),
            "type": register_data.pop("participant_type", {}).get("code", "PARTICIPANT"),
            "dates": register_data.pop("dates", {}),
            "consents": register_data.pop("consents", {}),
            # flatten
            # "medical_conditions": [condition.get('name', '') for condition in medical_info],
            "emergency_contacts": [self.filter_emergency_contact(contact) for contact in register_data.pop("emergency_contacts", [])],
            # "allergies": [condition.get('name', '') for condition in allergies],
            "medical_conditions": medical_info,
            "allergies": allergies,
            # only pick the most recent to show
            "payment_details": payment_details,
            "questions": answers_data,
            "verified": payment_details.get("verified", False)
        }
        
        
        data["registration"] = registration_data
        
        user_serializer = SimplifiedCommunityUserSerializer(user)
        user_data = user_serializer.data
        user_data["primary_email"] = user.primary_email
        data["user"] = user_data
        
        # show only carts relating to that event, and also show carts that are created by admin 
        carts = EventCart.objects.filter(user=user, event=event).exclude(active=True, created_via_admin=False) 
        cart_serializer = EventCartMinimalSerializer(carts, many=True)
        data["merch"] = cart_serializer.data        
    
        resources = event_data.pop("resources", [])
        data["resources"] = resources
        participant_questions = ParticipantQuestion.objects.filter(participant=event_participant, event=event)
        participant_question_serializer = ParticipantQuestionSerializer(participant_questions, many=True)
        
        data["questions"] = [self.filter_question(q) for q in participant_question_serializer.data]

        return Response(data, status=status.HTTP_200_OK)
    
    @staticmethod
    def get_full_address(venue):
        address_parts = [
            venue.get('address_line_1', ''),
            venue.get('address_line_2', ''),
            venue.get('address_line_3', ''),
            venue.get('postcode', ''),
            venue.get('country', '')
        ]
        return ', '.join(part for part in address_parts if part)
    
    @staticmethod
    def filter_emergency_contact(contact):
        contact.pop("id", None)
        contact.pop("contact_relationship", None)
        relation = contact.pop("contact_relationship_display", None)
        contact["relation"] = relation
        return contact
    
    @staticmethod
    def filter_question(question):
        question.pop("admin_notes", None)
        question.pop("priority", None)
        question.pop("questions_type", None)
        question.pop("status", None)
        question.pop("participant_details", None)
        question.pop("participant", None)
        question.pop("event", None)
        return question
    
    @action(detail=False, methods=['get'], url_name="my-events", url_path="my-events")
    def my_events(self, request):
        '''
        Retrieve a list of events that the user is involved in (created, supervisor, participant, service team member).
        
        Query params:
        - simple: 'true' for simplified serializer (default: 'true')
        - include_completed: 'true' to include COMPLETED events (default: 'true')
        - filter_by: 'created', 'participant', 'service_team', 'upcoming', 'ongoing', 'past', 'archived' (default: all)
        - role_id: Filter service team events by specific role UUID
        - event_type: Filter by event type (e.g., 'YOUTH_CAMP', 'CONFERENCE', etc.)
        - status: Filter by event status
        - search: Search by event name (case-insensitive partial match)
        - page: Page number for pagination
        - page_size: Number of results per page (default: 10)
        '''
        simple = request.query_params.get('simple', 'true').lower() == 'true'
        include_completed = request.query_params.get('include_completed', 'true').lower() == 'true'
        filter_by = request.query_params.get('filter_by', 'all')
        role_id = request.query_params.get('role_id', None)
        event_type = request.query_params.get('event_type', None)
        event_status = request.query_params.get('status', None)
        search_query = request.query_params.get('search', None)
        
        user = request.user
        if not user.is_authenticated:
            return Response(
                {'error': _('Authentication credentials were not provided.')},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Base query - exclude DELETED and PENDING_DELETION events (soft deleted)
        events = Event.objects.exclude(
            status__in=[Event.EventStatus.DELETED, Event.EventStatus.PENDING_DELETION]
        ).filter(date_for_deletion__isnull=True)
        
        # Get current date for time-based filters
        from django.utils import timezone
        today = timezone.now().date()
        
        # Apply role-based filtering first
        if filter_by == 'created':
            events = events.filter(created_by=user)
        elif filter_by == 'participant':
            events = events.filter(participants__user=user)
        elif filter_by == 'service_team':
            if role_id:
                # Filter by specific role
                events = events.filter(
                    service_team_members__user=user,
                    service_team_members__roles__id=role_id
                )
            else:
                # All service team events
                events = events.filter(service_team_members__user=user)
        elif filter_by == 'upcoming':
            # Events that haven't started yet (start_date > today)
            events = events.filter(
                models.Q(created_by=user) |
                models.Q(participants__user=user) |
                models.Q(service_team_members__user=user),
                start_date__gt=today
            ).exclude(status__in=[Event.EventStatus.COMPLETED, Event.EventStatus.ARCHIVED])
        elif filter_by == 'ongoing':
            # Events currently happening (start_date <= today <= end_date OR status=ONGOING)
            events = events.filter(
                models.Q(created_by=user) |
                models.Q(participants__user=user) |
                models.Q(service_team_members__user=user)
            ).filter(
                models.Q(status=Event.EventStatus.ONGOING) |
                models.Q(start_date__lte=today, end_date__gte=today)
            )
        elif filter_by == 'past':
            # Show COMPLETED events only
            events = events.filter(
                models.Q(created_by=user) |
                models.Q(participants__user=user) |
                models.Q(service_team_members__user=user),
                status=Event.EventStatus.COMPLETED
            )
        elif filter_by == 'archived':
            # Show ARCHIVED events only
            events = events.filter(
                models.Q(created_by=user) |
                models.Q(participants__user=user) |
                models.Q(service_team_members__user=user),
                status=Event.EventStatus.ARCHIVED
            )
        else:
            # 'all' - show events where user is involved (excluding COMPLETED and ARCHIVED by default)
            events = events.filter(
                models.Q(created_by=user) |
                models.Q(participants__user=user) |
                models.Q(service_team_members__user=user)
            )
            
            # Optionally exclude COMPLETED and ARCHIVED events from default view
            if not include_completed:
                events = events.exclude(status__in=[Event.EventStatus.COMPLETED, Event.EventStatus.ARCHIVED])
        
        # Apply event type filter
        if event_type:
            events = events.filter(event_type=event_type)
        
        # Apply status filter
        if event_status:
            events = events.filter(status=event_status)
        
        # Apply search filter (case-insensitive name search)
        if search_query:
            events = events.filter(name__icontains=search_query)
        
        # Remove duplicates and order
        events = events.distinct().order_by('-start_date')
        
        page = self.paginate_queryset(events)
        if page is not None:
            if simple:
                serializer = UserAwareEventSerializer(page, many=True, context={'request': request})
            else:
                serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        if simple:
            serializer = UserAwareEventSerializer(events, many=True, context={'request': request})
        else:
            serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)
    
    # participant related actions
    @action(detail=True, methods=['get'])
    def participants(self, request, pk=None, id=None):
        '''
        Retrieve a list of participants for a specific event.
        
        Supports filtering and ordering:
        - ?area=chapter/area/cluster_<id> (filter by area, chapter, or cluster)
        - ?bank_reference= (filter by bank reference in payments)
        - ?outstanding_payments=true/false (filter by payment status)
        - ?identity= (filter by name, email, or phone)
        - ?status= (filter by participant status)
        - ?order_by=recent_updates (order by most recent activity)
        - ?search= (general search across multiple fields)
        - ?page= (page number, default: 1)
        - ?page_size= (items per page, default: 10 from REST_FRAMEWORK settings)
        '''
        # Handle both pk and id parameters from DRF routing
        event_lookup = id if id is not None else pk
        print(f"🚀 Using event lookup: {event_lookup} (pk={pk}, id={id})")
        print(f"� PARTICIPANTS METHOD CALLED - pk: {pk}, query_params: {dict(request.query_params)}")
        print(f"�🔍 DEBUG participants - pk parameter: {pk}")
        print(f"🔍 DEBUG participants - request user: {request.user}")
        print(f"🔍 DEBUG participants - user is_superuser: {request.user.is_superuser}")
        print(f"🔍 DEBUG participants - user is_encoder: {getattr(request.user, 'is_encoder', False)}")
        

        queryset = self.get_queryset()
        print(f"🔍 DEBUG participants - queryset count: {queryset.count()}")
        # print(f"🔍 DEBUG participants - queryset SQL: {queryset.query}")
        
        # Debug: Check the raw Event count vs queryset count
        all_events_count = Event.objects.all().count()
        print(f"🔍 DEBUG participants - total events in DB: {all_events_count}")
        
        # Debug: Check if there are duplicate events with the same id
        if event_lookup:
            matching_events = queryset.filter(id=event_lookup)
            print(f"🔍 Events matching id '{event_lookup}': {matching_events.count()}")
            
            # Also check all events with this ID in the entire database
            all_matching = Event.objects.filter(id=event_lookup)
            print(f"🔍 ALL events in DB with id '{event_lookup}': {all_matching.count()}")
            
            if matching_events.count() > 1:
                print(f"⚠️ WARNING: Multiple events found with id '{event_lookup}' in filtered queryset")
                for i, event in enumerate(matching_events):
                    print(f"   - Event {i+1}: {event.name} (id: {event.id})")
                    
            if all_matching.count() > 1:
                print(f"⚠️ WARNING: Multiple events found with id '{event_lookup}' in ENTIRE database")
                for i, event in enumerate(all_matching):
                    print(f"   - DB Event {i+1}: {event.name} (id: {event.id})")
        print("⚠️ Query parameters:", dict(request.query_params))
        # Get event object directly instead of using self.get_object() which seems to have issues with query params
        try:
            print(f"🔍 DEBUG participants - About to get event directly using event_lookup: {event_lookup}")
            event = queryset.get(id=event_lookup)
            print(f"🔍 DEBUG participants - Successfully retrieved event: {event.name} (id: {event.id})")
        except Event.MultipleObjectsReturned as e:
            # Handle the case where multiple events are returned
            print(f"❌ ERROR: Multiple events returned for id '{event_lookup}': {str(e)}")
            matching_events = queryset.filter(id=event_lookup)
            print(f"   Total matching events in queryset: {matching_events.count()}")
            for i, evt in enumerate(matching_events):
                print(f"   Event {i+1}: {evt.name} (id: {evt.id})")
            # Use the first event as a fallback
            event = matching_events.first()
            print(f"   Using first event: {event.name} (id: {event.id})")
        except Event.DoesNotExist as e:
            print(f"❌ ERROR: Event not found for id '{event_lookup}': {str(e)}")
            return Response({'error': 'Event not found'}, status=404)
        except Exception as unexpected_error:
            print(f"❌ UNEXPECTED ERROR in get_object(): {unexpected_error}")
            print(f"❌ Error type: {type(unexpected_error)}")
            import traceback
            traceback.print_exc()
            return Response({'error': f'Unexpected error: {str(unexpected_error)}'}, status=500)
        
        simple = request.query_params.get('simple', 'true').lower() == 'true'
        order_by = request.query_params.get('order_by', 'registration_date')
        
        query_params = []
        
        # Enhanced search functionality
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__primary_email__icontains=search) |
                Q(user__phone_number__icontains=search) |
                Q(event_pax_id__icontains=search_upper) |
                Q(participant_event_payments__bank_reference__icontains=search_upper) |
                Q(user__product_payments__bank_reference__icontains=search_upper)
            )
        
        # Identity filter (exact or partial match)
        identity = request.query_params.get("identity")
        if identity:
            identity_upper = identity.upper()
            query_params.append(
                Q(user__first_name__icontains=identity) |
                Q(user__last_name__icontains=identity) |
                Q(user__primary_email__icontains=identity) |
                Q(user__phone_number__icontains=identity) |
                Q(event_pax_id__icontains=identity_upper)
            )
        
        # Area filtering - support multiple values
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__area_from__area_name__icontains=area) |
                        Q(user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
            
        # Chapter filtering - support multiple values
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    print(f"🔍 DEBUG participants - Applying chapter filter: '{chapter}'")
                    chapter_queries.append(Q(user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
            
        # Cluster filtering - support multiple values
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    print(f"🔍 DEBUG participants - Applying cluster filter: '{cluster}'")
                    cluster_queries.append(Q(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
            
        # Bank reference filter (for both event and product payments)
        # This handles bank_reference, event_payment_tracking_number, and payment_reference_id
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(participant_event_payments__bank_reference__icontains=bank_reference_upper) |
                Q(participant_event_payments__event_payment_tracking_number__icontains=bank_reference_upper) |
                Q(user__product_payments__bank_reference__icontains=bank_reference_upper) |
                Q(user__product_payments__payment_reference_id__icontains=bank_reference_upper)
            )
        
        # Payment method filter (for both event and product payments)
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            payment_method_upper = payment_method.upper()
            query_params.append(
                Q(participant_event_payments__method__method__iexact=payment_method_upper) |
                Q(user__product_payments__method__method__iexact=payment_method_upper)
            )
        
        # Payment package filter (for event payments only)
        payment_package = request.query_params.get("payment_package")
        if payment_package:
            try:
                package_id = uuid.UUID(payment_package)
                query_params.append(Q(participant_event_payments__package__id=package_id))
            except (ValueError, TypeError):
                # If not a valid UUID, try to filter by package name
                query_params.append(Q(participant_event_payments__package__name__icontains=payment_package))
            
        # Has merchandise filter
        has_merch = request.query_params.get("has_merch")
        if has_merch:
            if has_merch.lower() == 'true':
                # Participants with merchandise orders
                query_params.append(Q(user__carts__event=event))
            elif has_merch.lower() == 'false':
                # Participants without merchandise orders
                query_params.append(~Q(user__carts__event=event))
                
        # Registration date filter
        registration_date = request.query_params.get("registration_date")
        if registration_date:
            try:
                from datetime import datetime
                filter_date = datetime.fromisoformat(registration_date.replace('Z', '+00:00'))
                query_params.append(Q(registration_date__date=filter_date.date()))
            except ValueError:
                print(f"⚠️ Invalid registration_date format: {registration_date}")
                pass
            
        # Status filter
        status = request.query_params.get("status")
        if status:
            status_upper = status.upper()
            # Handle status filtering - check if it's a direct field or needs special handling
            if status_upper in ['REGISTERED', 'CONFIRMED', 'CANCELLED']:
                query_params.append(Q(status__iexact=status_upper))
            elif status_upper == 'CHECKED_IN':
                # Special case for checked in participants based on attendance
                from apps.events.models import EventDayAttendance
                from datetime import date
                today = date.today()
                query_params.append(
                    Q(user__event_attendance__check_in_time__date=today) &
                    Q(user__event_attendance__check_in_time__isnull=False) &
                    Q(user__event_attendance__check_out_time__isnull=True)
                )
            elif status_upper == 'NOT_CHECKED_IN':
                # Participants without check-in today
                from apps.events.models import EventDayAttendance
                from datetime import date
                today = date.today()
                query_params.append(
                    ~Q(user__event_attendance__check_in_time__date=today, 
                       user__event_attendance__check_in_time__isnull=False)
                )
            
        # Outstanding payments filter
        outstanding_payments = request.query_params.get("outstanding_payments")
        if outstanding_payments:
            if outstanding_payments.lower() == 'true':
                # Participants with outstanding payments/orders
                query_params.append(
                    Q(participant_event_payments__event=event, participant_event_payments__verified=False) |
                    Q(participant_event_payments__event=event, participant_event_payments__status=EventPayment.PaymentStatus.FAILED) |
                    Q(user__carts__event=event, user__carts__submitted=True, user__carts__approved=False, user__carts__active=True)
                )
            elif outstanding_payments.lower() == 'false':
                # Participants without outstanding payments/orders
                query_params.append(
                    ~Q(participant_event_payments__event=event, participant_event_payments__verified=False) &
                    ~Q(participant_event_payments__event=event, participant_event_payments__status=EventPayment.PaymentStatus.FAILED) &
                    ~Q(user__carts__event=event, user__carts__submitted=True, user__carts__approved=False, user__carts__active=True)
                )
        
        # Extra questions filtering
        # Format: ?extra_questions=<question_id>:<choice_id_or_text>,<question_id>:<choice_id_or_text>
        extra_questions_param = request.query_params.get("extra_questions")
        if extra_questions_param:
            question_filters = extra_questions_param.split(",")
            for question_filter in question_filters:
                try:
                    question_id, answer_value = question_filter.split(":", 1)
                    question_id = question_id.strip()
                    answer_value = answer_value.strip()
                    
                    # Try to parse as UUID (for choice-based answers)
                    if test_safe_uuid(answer_value):
                        # Filter by selected choice
                        query_params.append(
                            Q(event_question_answers__question__id=uuid.UUID(question_id)) &
                            Q(event_question_answers__selected_choices__id=uuid.UUID(answer_value))
                        )
                    else:
                        # Filter by text answer
                        query_params.append(
                            Q(event_question_answers__question__id=uuid.UUID(question_id)) &
                            Q(event_question_answers__answer_text__icontains=answer_value)
                        )
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Error parsing extra question filter '{question_filter}': {e}")
                    continue
            
        # Legacy questions_match parameter (keep for backwards compatibility)
        questions = request.query_params.get("questions_match")
        if questions:
            question_split = questions.split(",")
            for key_pair in question_split:
                try:
                    question_id, answer = key_pair.split("=")
                    answer = answer.strip()
                    
                    if test_safe_uuid(answer):
                        query_params.append(
                                Q(event_question_answers__question=uuid.UUID(question_id), event_question_answers__selected_choices=answer)
                            )
                    else:
                        query_params.append(
                            Q(event_question_answers__question=uuid.UUID(question_id), event_question_answers__answer_text=answer)
                            )
                except TypeError:
                    raise serializers.ValidationError("could not parse query correctly")
        try:
            # Base queryset with optimized joins
            participants = event.participants.select_related(
                'user', 'user__area_from', 'user__area_from__unit__chapter', 
                'user__area_from__unit__chapter__cluster'
            ).prefetch_related(
                'participant_event_payments', 'user__product_payments', 
                'user__carts', 'event_question_answers'
            )
            
            print(f"🔍 DEBUG participants - Base queryset count: {participants.count()}")
            
            # Apply filters
            if query_params:
                print(f"🔍 DEBUG participants - Applying {len(query_params)} filter(s)")
                for i, q in enumerate(query_params):
                    print(f"   Filter {i+1}: {q}")
                
                participants = participants.filter(*query_params).distinct()
                print(f"🔍 DEBUG participants - Filtered queryset count: {participants.count()}")
                # print(f"🔍 DEBUG participants - SQL Query: {participants.query}")
            else:
                print(f"🔍 DEBUG participants - No filters applied")
            
            # Apply ordering
            if order_by == 'recent_updates':
                # Order by most recent activity (payments, registrations) - simplified to avoid cross-model issues
                from django.db.models import Max, DateTimeField
                from django.db.models.functions import Coalesce
                
                # Simplified approach - avoid cross-model annotations that might cause select_related issues
                participants = participants.annotate(
                    last_payment_date=Max('participant_event_payments__created_at'),
                    # Use registration_date as baseline for comparison
                    activity_score=Coalesce('last_payment_date', 'registration_date', output_field=DateTimeField())
                ).order_by(
                    # Order by most recent payments/registrations
                    '-activity_score',
                    # Finally by registration date as fallback
                    '-registration_date'
                )
            elif order_by == 'name':
                participants = participants.order_by('user__first_name', 'user__last_name')
            elif order_by == 'registration_date':
                participants = participants.order_by('-registration_date')
            else:
                # Default ordering
                participants = participants.order_by('-registration_date')
                
        except (ValueError, ValidationError) as e:
            print(f"❌ ERROR in participants filtering: {e}")
            raise serializers.ValidationError("Invalid query parameters: " + str(e))
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR in participants filtering: {e}")
            print(f"❌ Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError("Error processing participants: " + str(e))

        # Get available filter options for dropdowns (from all participants, not filtered ones)
        try:
            all_participants = event.participants.select_related(
                'user', 'user__area_from', 'user__area_from__unit__chapter', 
                'user__area_from__unit__chapter__cluster'
            ).distinct()
            
            # Extract unique areas, chapters, and clusters for filter dropdowns
            areas = set()
            chapters = set()
            clusters = set()
            
            print(f"🔍 Processing {all_participants.count()} participants for filter options")
            
            for participant in all_participants:
                try:
                    user = participant.user
                    if user and hasattr(user, 'area_from') and user.area_from:
                        area_from = user.area_from
                        
                        # Area name
                        if hasattr(area_from, 'area_name') and area_from.area_name:
                            areas.add(area_from.area_name)
                            
                        # Chapter name (via unit.chapter)
                        if hasattr(area_from, 'unit') and area_from.unit:
                            unit = area_from.unit
                            if hasattr(unit, 'chapter') and unit.chapter:
                                chapter = unit.chapter
                                if hasattr(chapter, 'chapter_name') and chapter.chapter_name:
                                    chapters.add(chapter.chapter_name)
                                    
                                # Cluster name (via chapter.cluster)
                                if hasattr(chapter, 'cluster') and chapter.cluster:
                                    cluster = chapter.cluster
                                    if hasattr(cluster, 'cluster_id') and cluster.cluster_id:
                                        clusters.add(cluster.cluster_id)
                except Exception as e:
                    print(f"⚠️ Error processing participant {participant.id}: {e}")
                    continue
            
            print(f"📊 Filter options found - Areas: {len(areas)}, Chapters: {len(chapters)}, Clusters: {len(clusters)}")
            
            filter_options = {
                'areas': sorted(list(areas)),
                'chapters': sorted(list(chapters)), 
                'clusters': sorted(list(clusters))
            }
            
        except Exception as e:
            print(f"❌ Error building filter options: {e}")
            filter_options = {
                'areas': [],
                'chapters': [], 
                'clusters': []
            }

        # Apply pagination
        page = self.paginate_queryset(participants)        
        if page is not None:
            if simple:
                serializer = ListEventParticipantSerializer(page, many=True)
            else:
                serializer = ParticipantManagementSerializer(page, many=True)
            
            # Get paginated response and add filter options
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data['filter_options'] = filter_options
            return paginated_response
        
        # Return all results if pagination is disabled
        if simple:
            serializer = ListEventParticipantSerializer(participants, many=True)
        else:
            serializer = ParticipantManagementSerializer(participants, many=True)
        
        return Response({
            'results': serializer.data,
            'filter_options': filter_options
        })
    
    @action(detail=True, methods=['get'], url_name="event-payments", url_path="event-payments")
    def event_payments(self, request, pk=None, id=None):
        '''
        Retrieve a list of event payments for a specific event with filtering support.
        
        Supports the same filtering as participants:
        - ?search= (search by name, email, tracking number, bank reference)
        - ?bank_reference= (filter by bank reference or tracking number)
        - ?payment_method= (filter by payment method: STRIPE, BANK, CASH, etc.)
        - ?payment_package= (filter by package ID or name)
        - ?status= (filter by payment status: PENDING, SUCCEEDED, FAILED)
        - ?verified=true/false (filter by verification status)
        - ?area= (filter by participant's area)
        - ?chapter= (filter by participant's chapter)
        - ?cluster= (filter by participant's cluster)
        '''
        from apps.events.api.serializers import EventPaymentListSerializer
        
        event_lookup = id if id is not None else pk
        event = self.get_queryset().get(id=event_lookup)
        
        # Build query filters
        query_params = []
        
        # Always filter by event
        query_params.append(Q(event=event))
        
        # Search across multiple fields
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__user__first_name__icontains=search) |
                Q(user__user__last_name__icontains=search) |
                Q(user__user__primary_email__icontains=search) |
                Q(event_payment_tracking_number__icontains=search_upper) |
                Q(bank_reference__icontains=search_upper)
            )
        
        # Bank reference filter
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(bank_reference__icontains=bank_reference_upper) |
                Q(event_payment_tracking_number__icontains=bank_reference_upper)
            )
        
        # Payment method filter
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            query_params.append(Q(method__method__iexact=payment_method.upper()))
        
        # Payment package filter
        payment_package = request.query_params.get("payment_package")
        if payment_package:
            try:
                package_id = uuid.UUID(payment_package)
                query_params.append(Q(package__id=package_id))
            except (ValueError, TypeError):
                query_params.append(Q(package__name__icontains=payment_package))
        
        # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            query_params.append(Q(status__iexact=status_param.upper()))
        
        # Verified filter
        verified = request.query_params.get("verified")
        if verified:
            query_params.append(Q(verified=(verified.lower() == 'true')))
        
        # Area filtering
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__user__area_from__area_name__icontains=area) |
                        Q(user__user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
        
        # Chapter filtering
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    chapter_queries.append(Q(user__user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
        
        # Cluster filtering
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    cluster_queries.append(Q(user__user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
        
        # Build queryset
        payments = EventPayment.objects.select_related(
            'user', 'user__user', 'user__user__area_from',
            'user__user__area_from__unit__chapter',
            'user__user__area_from__unit__chapter__cluster',
            'method', 'package', 'event'
        ).filter(*query_params).distinct().order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(payments)
        if page is not None:
            serializer = EventPaymentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventPaymentListSerializer(payments, many=True)
        return Response({'results': serializer.data})
    
    @action(detail=True, methods=['get'], url_name="product-payments", url_path="product-payments")
    def product_payments(self, request, pk=None, id=None):
        '''
        Retrieve a list of product payments (cart payments) for a specific event with filtering support.
        
        Supports the same filtering as participants:
        - ?search= (search by name, email, payment reference, bank reference)
        - ?bank_reference= (filter by bank reference or payment reference)
        - ?payment_method= (filter by payment method: STRIPE, BANK, CASH, etc.)
        - ?status= (filter by payment status: PENDING, SUCCEEDED, FAILED)
        - ?approved=true/false (filter by approval status)
        - ?area= (filter by user's area)
        - ?chapter= (filter by user's chapter)
        - ?cluster= (filter by user's cluster)
        '''
        from apps.shop.api.serializers import ProductPaymentListSerializer
        
        event_lookup = id if id is not None else pk
        event = self.get_queryset().get(id=event_lookup)
        
        # Build query filters
        query_params = []
        
        # Always filter by event (through cart)
        query_params.append(Q(cart__event=event))
        
        # Search across multiple fields
        search = request.query_params.get("search")
        if search:
            search_upper = search.upper()
            query_params.append(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__primary_email__icontains=search) |
                Q(payment_reference_id__icontains=search_upper) |
                Q(bank_reference__icontains=search_upper) |
                Q(cart__order_reference_id__icontains=search_upper)
            )
        
        # Bank reference filter
        bank_reference = request.query_params.get("bank_reference")
        if bank_reference:
            bank_reference_upper = bank_reference.upper()
            query_params.append(
                Q(bank_reference__icontains=bank_reference_upper) |
                Q(payment_reference_id__icontains=bank_reference_upper)
            )
        
        # Payment method filter
        payment_method = request.query_params.get("payment_method")
        if payment_method:
            query_params.append(Q(method__method__iexact=payment_method.upper()))
        
        # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            query_params.append(Q(status__iexact=status_param.upper()))
        
        # Approved filter
        approved = request.query_params.get("approved")
        if approved:
            query_params.append(Q(approved=(approved.lower() == 'true')))
        
        # Area filtering
        areas = request.query_params.getlist("area")
        if areas:
            area_queries = []
            for area in areas:
                if area and area.strip():
                    area_queries.append(
                        Q(user__area_from__area_name__icontains=area) |
                        Q(user__area_from__area_code__icontains=area)
                    )
            if area_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, area_queries))
        
        # Chapter filtering
        chapters = request.query_params.getlist("chapter")
        if chapters:
            chapter_queries = []
            for chapter in chapters:
                if chapter and chapter.strip():
                    chapter_queries.append(Q(user__area_from__unit__chapter__chapter_name__icontains=chapter))
            if chapter_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, chapter_queries))
        
        # Cluster filtering
        clusters = request.query_params.getlist("cluster")
        if clusters:
            cluster_queries = []
            for cluster in clusters:
                if cluster and cluster.strip():
                    cluster_queries.append(Q(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
            if cluster_queries:
                from functools import reduce
                import operator
                query_params.append(reduce(operator.or_, cluster_queries))
        
        # Build queryset
        payments = ProductPayment.objects.select_related(
            'user', 'user__area_from',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster',
            'method', 'package', 'cart', 'cart__event'
        ).prefetch_related(
            'cart__orders'
        ).filter(*query_params).distinct().order_by('-created_at')
        
        # Apply pagination
        page = self.paginate_queryset(payments)
        if page is not None:
            serializer = ProductPaymentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ProductPaymentListSerializer(payments, many=True)
        return Response({'results': serializer.data})
    
    @action(detail=True, methods=['post'], url_name="register", url_path="register")
    def register(self, request, id=None):
        '''
        Register a user for a specific event.
        '''
        event = self.get_object()
        user = request.user
        self.check_object_permissions(request, event) # Ensure user has permission to register
        self.check_permissions(request) # Ensure user is authenticated
        
        if EventParticipant.objects.filter(event=event, user=user).exists():
            return Response(
                {'error': _('You are already registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        participant_type =  request.data.get('participant_type', EventParticipant.ParticipantType.PARTICIPANT)
        if participant_type not in dict(EventParticipant.ParticipantType.choices):
            return Response(
                {'error': _('Invalid participant type.')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if participant_type == EventParticipant.ParticipantType.SERVICE_TEAM:
            # generally service team registration should not be done this way
            # only event organizers/admins should be able to register themselves as ST
            if user.has_perm('events.add_eventserviceteammember'):
                service_team, created = EventServiceTeamMember.objects.get_or_create(event=event, user=user)
                if not created:
                    return Response(
                        {'error': _('You are already registered as a service team member for this event.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                service_team.roles.set(request.data.get('role_ids', []))
                return Response(
                    {'message': _('Successfully registered as a service team member.')},
                    status=status.HTTP_201_CREATED
                ) 
            else:
                return Response(
                    {'error': _('Service team registration is not allowed via this endpoint.')},
                    status=status.HTTP_400_BAD_REQUEST
                ) 
            
        participant = EventParticipant.objects.create(
            event=event,
            user=user,
            status=EventParticipant.ParticipantStatus.REGISTERED,
            participant_type=participant_type
        )
        
        # Broadcast WebSocket update for new participant registration
        try:
            participant_data = serialize_participant_for_websocket(participant)
            websocket_notifier.notify_participant_registered(
                event_id=str(event.id),
                participant_data=participant_data
            )
            
            # Notify dashboard users about participant count change
            supervisor_ids = get_event_supervisors(event)
            websocket_notifier.notify_event_update(
                user_ids=supervisor_ids,
                event_id=str(event.id),
                update_type='participant_registered',
                data={'participant_id': str(participant.id)}
            )
        except Exception as e:
            # Log the error but don't fail the registration process
            print(f"WebSocket notification error during registration: {e}")
        
        serializer = SimplifiedEventParticipantSerializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name="remove-participant", url_path="remove-participant")
    def remove_participant(self, request, id=None):
        '''
        Remove a participant from the event.
        '''
        event = self.get_object()
        user = request.user
        self.check_object_permissions(request, event)  # Ensure user has permission to remove
        try:
            participant = EventParticipant.objects.get(event=event, user=user)
        except EventParticipant.DoesNotExist:
            return Response(
                {'error': _('You are not registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        participant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'], url_name="attendance", url_path="attendance")
    def attendance(self, request, id=None):
        '''
        Retrieve a list of attendance records for a specific event.
        '''
        event = self.get_object()
        attendance_records = event.attendance_records.all()
        page = self.paginate_queryset(attendance_records)
        if page is not None:
            serializer = EventDayAttendanceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventDayAttendanceSerializer(attendance_records, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path="service-team")
    def service_team(self, request, id=None):
        '''
        Retrieve a list of service team members for a specific event.
        '''
        event = self.get_object()
        service_team = event.service_team_members.all()
        page = self.paginate_queryset(service_team)
        if page is not None:
            serializer = EventServiceTeamMemberSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventServiceTeamMemberSerializer(service_team, many=True)
        return Response(serializer.data)
    
    # service team related actions
    
    @action(detail=True, methods=['post'], url_name="add-service-member", url_path="add-service-member")
    def add_service_member(self, request, id=None):
        '''
        Add a service team member to a specific event.
        {"member_id": "member-uuid", "role_ids": [role_uuid1, role_uuid2], "head_of_role": true}
        '''
        event = self.get_object()
        member_id = request.data.get('member_id')
        role_ids = request.data.get('role_ids', [])
        
        self.check_object_permissions(request, event) 
        self.check_permissions(request) 
        
        if not member_id:
            return Response(
                {'error': _('Member ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # avoid using real uuid, use member_id instead
            user = get_user_model().objects.get(member_id=member_id)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if EventServiceTeamMember.objects.filter(event=event, user=user).exists():
            return Response(
                {'error': _('User is already a service team member for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service_member = EventServiceTeamMember.objects.create(
            event=event,
            user=user,
            head_of_role=request.data.get('head_of_role', False)
        )
        
        if role_ids:
            roles = EventRole.objects.filter(id__in=role_ids)
            service_member.roles.set(roles)
        
        serializer = EventServiceTeamMemberSerializer(service_member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_name="remove-service-member", url_path="remove-service-member")
    def remove_service_member(self, request, id=None):
        '''
        Remove a service team member from a specific event.
        {"member_id": "member-uuid"}
        '''
        event = self.get_object()
        member_id = request.data.get('member_id')
        
        self.check_object_permissions(request, event) 
        self.check_permissions(request) 
        
        if not member_id:
            return Response(
                {'error': _('Member ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = get_user_model().objects.get(member_id=member_id)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            service_member = EventServiceTeamMember.objects.get(event=event, user=user)
        except EventServiceTeamMember.DoesNotExist:
            return Response(
                {'error': _('User is not a service team member for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        service_member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    # metadata related actions
    
    @action(detail=True, methods=['get'])
    def talks(self, request, id=None):
        '''
        Retrieve a list of talks for a specific event.
        '''
        event = self.get_object()
        talks = event.talks.all()
        page = self.paginate_queryset(talks)
        if page is not None:
            serializer = EventTalkSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventTalkSerializer(talks, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def workshops(self, request, id=None):
        '''
        Retrieve a list of workshops for a specific event.
        '''
        event = self.get_object()
        workshops = event.workshops.all()
        page = self.paginate_queryset(workshops)
        if page is not None:
            serializer = EventWorkshopSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = EventWorkshopSerializer(workshops, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_name="resources", url_path="resources")
    def resources(self, request, pk=None):
        '''
        Retrieve a list of resources for a specific event.
        '''
        event = self.get_object()
        resources = event.resources.all()
        page = self.paginate_queryset(resources)
        if page is not None:
            serializer = PublicEventResourceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PublicEventResourceSerializer(resources, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_name="products", url_path="products")
    def products(self, request, id=None):
        '''
        Retrieve a list of products for a specific event with user-specific discounts.
        
        For authenticated service team members, calculates discounts using cascading priority:
        1. Individual product discount (EventServiceTeamMember.product_discount)
        2. Role-based product discount (EventRoleDiscount.product_discount)
        3. General product discount (EventProduct.discount_for_service_team)
        '''
        from decimal import Decimal
        from apps.events.models import EventServiceTeamMember, EventRoleDiscount
        
        event = self.get_object()
        now = timezone.now()
        
        products = event.products.filter(
                Q(preview_date__isnull=True, release_date__isnull=True) |
                Q(preview_date__lte=now) |  
                Q(preview_date__isnull=True, release_date__lte=now)
                )
        
        # Calculate user-specific discounts if user is authenticated service team member
        discount_data = {}
        if request.user and request.user.is_authenticated:
            try:
                service_team_member = EventServiceTeamMember.objects.get(
                    user=request.user,
                    event=event
                )
                
                # Get user's role-based discounts for this event (user can have multiple roles)
                role_discounts = EventRoleDiscount.objects.filter(
                    event=event,
                    role__in=service_team_member.roles.all()
                )
                # Calculate discount for each product
                for product in products:
                    discount_info = self._calculate_product_discount(
                        product, 
                        service_team_member, 
                        role_discounts
                    )
                    if discount_info:
                        discount_data[product.uuid] = discount_info
                        
            except EventServiceTeamMember.DoesNotExist:
                # User is not a service team member - no discounts
                pass
        
        # Serialize with discount data in context
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = EventProductSerializer(
                page, 
                many=True, 
                context={'request': request, 'product_discounts': discount_data}
            )
            return self.get_paginated_response(serializer.data)

        serializer = EventProductSerializer(
            products, 
            many=True, 
            context={'request': request, 'product_discounts': discount_data}
        )
        return Response(serializer.data)
    
    def _calculate_product_discount(self, product, service_team_member, role_discounts):
        """
        Calculate the applicable discount for a product using cascading priority.
        
        Priority (Service Team Members Only):
        1. Individual product discount (EventServiceTeamMember.product_discount) - Highest
        2. Role-based product discount (EventRoleDiscount.product_discount) - Best among all roles
        3. Product-specific discount (EventProduct.discount_for_service_team)
        4. Event-level product discount (Event.product_discount) - Final fallback
        
        Returns:
            dict: Discount information with keys:
                - discount_amount: Decimal amount to subtract
                - discounted_price: Final price after discount
                - discount_type: 'PERCENTAGE' or 'FIXED'
                - discount_value: The discount value
                - source: 'individual', 'role', 'product', or 'event'
                - role_name: Role display name (only for role-based discounts)
        """
        from decimal import Decimal
        
        original_price = Decimal(str(product.price))
        
        # Priority 1: Individual product discount
        if service_team_member.product_discount_type and service_team_member.product_discount_value:
            discount_amount = service_team_member.calculate_product_discount(original_price)
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return {
                    'discount_amount': discount_amount,
                    'discounted_price': final_price,
                    'discount_type': service_team_member.product_discount_type,
                    'discount_value': service_team_member.product_discount_value,
                    'source': 'individual'
                }
        
        # Priority 2: Role-based product discount (find the best discount among all roles)
        best_role_discount = None
        best_role_discount_amount = Decimal('0')
        
        for role_discount in role_discounts:
            if role_discount.has_product_discount:
                discount_amount = role_discount.calculate_product_discount(original_price)
                if discount_amount > best_role_discount_amount:
                    best_role_discount_amount = discount_amount
                    best_role_discount = role_discount
        
        if best_role_discount and best_role_discount_amount > 0:
            final_price = max(original_price - best_role_discount_amount, Decimal('0')).quantize(Decimal('0.01'))
            return {
                'discount_amount': best_role_discount_amount,
                'discounted_price': final_price,
                'discount_type': best_role_discount.product_discount_type,
                'discount_value': best_role_discount.product_discount_value,
                'source': 'role',
                'role_name': best_role_discount.role.get_role_name_display()
            }
        
        # Priority 3: Product-specific discount
        if product.has_service_team_discount:
            discount_amount = product.calculate_service_team_discount()
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return {
                    'discount_amount': discount_amount,
                    'discounted_price': final_price,
                    'discount_type': product.service_team_discount_type,
                    'discount_value': product.service_team_discount_value,
                    'source': 'product'
                }
        
        # Priority 4: Event-level product discount (final fallback for service team members)
        event = product.event
        if event.has_product_discount:
            discount_amount = event.calculate_product_discount(original_price)
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return {
                    'discount_amount': discount_amount,
                    'discounted_price': final_price,
                    'discount_type': event.product_discount_type,
                    'discount_value': event.product_discount_value,
                    'source': 'event'
                }
        
        return None

    @action(detail=True, methods=['get'], url_name="payment-methods", url_path="payment-methods")
    def product_payment_methods(self, request, pk=None):
        '''
        Retrieve a list of product payment methods for a specific event.
        '''
        event = self.get_object()
        payment_methods = event.product_payment_methods.all()
        page = self.paginate_queryset(payment_methods)
        if page is not None:
            serializer = EventPaymentMethodSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = EventPaymentMethodSerializer(payment_methods, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], url_name="product-payment-methods", url_path="product-payment-methods")
    def product_payment_methods(self, request, id=None):
        '''
        Retrieve and create merchandise payment methods for a specific event.
        '''
        if request.method == 'GET':
            event = self.get_object()
            payment_methods = event.product_payment_methods.filter(is_active=True)
            page = self.paginate_queryset(payment_methods)
            if page is not None:
                serializer = ProductPaymentMethodSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = ProductPaymentMethodSerializer(payment_methods, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            event = self.get_object()
            self.check_object_permissions(request, event) 
            self.check_permissions(request) 
            serializer = ProductPaymentMethodSerializer(data=request.data, context={'event': event})
            if serializer.is_valid():
                serializer.save(event=event)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['put', 'patch', 'delete'], url_name="product-payment-method-detail", url_path="product-payment-methods/(?P<method_id>[^/.]+)")
    def product_payment_method_detail(self, request, id=None, method_id=None):
        '''
        Update or delete a specific merchandise payment method for an event.
        '''
        event = self.get_object()
        self.check_object_permissions(request, event)
        self.check_permissions(request)
        
        try:
            payment_method = event.product_payment_methods.get(id=method_id)
        except event.product_payment_methods.model.DoesNotExist:
            return Response(
                {'error': _('Payment method not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method in ['PUT', 'PATCH']:
            serializer = ProductPaymentMethodSerializer(
                payment_method, 
                data=request.data, 
                partial=request.method == 'PATCH',
                context={'event': event}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            payment_method.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=["GET"], url_name="check-in-users", url_path="check-in-users")
    def get_check_in_users(self, request, id=None):
        '''
        To filter by cluster use ?area=cluster_d
        '''
        query_params = []
        
        area = request.query_params.get("area")
        if area:
            if area.startswith("cluster_"):
                cluster_id = area[-1].upper()
                print(cluster_id)
                query_params.append(Q(user__area_from__unit__chapter__cluster__cluster_id=cluster_id))
            else:
                query_params.append(
                    (Q(user__area_from__area_name=area) | Q(user__area_from__area_code=area) | 
                    Q(user__area_from__unit__chapter__chapter_name=area.capitalize())) 
                )
        participants = EventParticipant.objects.filter(
            (Q(user__event_attendance__stale=True) | Q(user__event_attendance=None)),
            event=id,
            *query_params,
        ).distinct()
        
        return Response([
            {
                "full_name": f"{p.user.first_name} {p.user.last_name}",
                "picture": p.user.profile_picture.url if p.user.profile_picture else None,
                "area": p.user.area_from.area_name if p.user.area_from else None,
                "chapter": p.user.area_from.unit.chapter.chapter_name if p.user.area_from and p.user.area_from.unit and p.user.area_from.unit.chapter else None,
                "cluster": p.user.area_from.unit.chapter.cluster.cluster_id if p.user.area_from and p.user.area_from.unit and p.user.area_from.unit.chapter and p.user.area_from.unit.chapter.cluster else None
            } for p in participants.all()
        ])
        
    @action(detail=True, methods=["GET"], url_name="filter-options", url_path="filter-options")
    def filter_options(self, request, id=None):
        """
        Get available filter options for participant filtering.
        Returns areas, chapters, clusters, and extra questions with their choices.
        """
        try:
            from apps.events.models.location_models import AreaLocation, ChapterLocation, ClusterLocation
            from apps.events.models import ExtraQuestion
            
            # Get the current event
            event = self.get_object()
            
            # Get areas, chapters, and clusters that have participants in this event
            participants_queryset = event.participants.all()
            
            # Extract unique location values from participants
            areas_with_participants = set()
            chapters_with_participants = set()
            clusters_with_participants = set()
            
            for participant in participants_queryset:
                if participant.user and participant.user.area_from:
                    area_obj = participant.user.area_from
                    if area_obj.area_name:
                        areas_with_participants.add(area_obj.area_name)
                    if area_obj.unit and area_obj.unit.chapter and area_obj.unit.chapter.chapter_name:
                        chapters_with_participants.add(area_obj.unit.chapter.chapter_name)
                    if area_obj.unit and area_obj.unit.chapter and area_obj.unit.chapter.cluster and area_obj.unit.chapter.cluster.cluster_id:
                        clusters_with_participants.add(area_obj.unit.chapter.cluster.cluster_id)
            
            # Convert to sorted lists
            areas = sorted(list(areas_with_participants))
            chapters = sorted(list(chapters_with_participants))
            clusters = sorted(list(clusters_with_participants))
            
            # Get extra questions for this event
            extra_questions = ExtraQuestion.objects.filter(event=event).prefetch_related('choices').order_by('order')
            
            extra_questions_data = []
            for question in extra_questions:
                question_data = {
                    'id': str(question.id),
                    'question_name': question.question_name,
                    'question_body': question.question_body,
                    'question_type': question.question_type,
                    'question_type_display': question.get_question_type_display(),
                    'required': question.required,
                    'order': question.order,
                    'choices': []
                }
                
                # Add choices for CHOICE and MULTICHOICE questions
                if question.question_type in ['CHOICE', 'MULTICHOICE']:
                    choices = question.choices.all().order_by('order')
                    question_data['choices'] = [
                        {
                            'id': str(choice.id),
                            'text': choice.text,
                            'value': choice.value or choice.text,
                            'order': choice.order
                        }
                        for choice in choices
                    ]
                
                extra_questions_data.append(question_data)
            
            return Response({
                'areas': areas,
                'chapters': chapters,
                'clusters': clusters,
                'extra_questions': extra_questions_data
            })
        except Exception as e:
            print(f"❌ Error getting filter options: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'areas': [],
                'chapters': [],
                'clusters': [],
                'extra_questions': []
            })

        
    @action(detail=True, methods=["GET"], url_name="questions-asked", url_path="questions-asked")
    def questions_asked(self, request, id=None, pk=None):
        """
        Get participant questions for a specific event with same filtering as participants.
        Supports the same filter parameters as the participants endpoint.
        """
        try:
            from apps.events.models import ParticipantQuestion
            from apps.events.api.serializers.registration_serializers import ParticipantQuestionSerializer
            
            # Get the current event - use direct lookup to avoid query param issues
            event_lookup = id if id is not None else pk
            queryset = self.get_queryset()
            
            try:
                event = queryset.get(id=event_lookup)
            except Event.DoesNotExist:
                return Response({'error': 'Event not found'}, status=404)
            
            query_params = []
            
            # Enhanced search functionality
            search = request.query_params.get("search")
            if search:
                search_upper = search.upper()
                query_params.append(
                    Q(participant__user__first_name__icontains=search) |
                    Q(participant__user__last_name__icontains=search) |
                    Q(participant__user__primary_email__icontains=search) |
                    Q(participant__event_pax_id__icontains=search_upper) |
                    Q(question_subject__icontains=search) |
                    Q(question__icontains=search)
                )
            
            # Identity filter
            identity = request.query_params.get("identity")
            if identity:
                identity_upper = identity.upper()
                query_params.append(
                    Q(participant__user__first_name__icontains=identity) |
                    Q(participant__user__last_name__icontains=identity) |
                    Q(participant__user__primary_email__icontains=identity) |
                    Q(participant__event_pax_id__icontains=identity_upper)
                )
            
            # Area filtering
            areas = request.query_params.getlist("area")
            if areas:
                area_queries = []
                for area in areas:
                    if area and area.strip():
                        area_queries.append(
                            Q(participant__user__area_from__area_name__icontains=area) |
                            Q(participant__user__area_from__area_code__icontains=area)
                        )
                if area_queries:
                    from functools import reduce
                    import operator
                    query_params.append(reduce(operator.or_, area_queries))
                
            # Chapter filtering
            chapters = request.query_params.getlist("chapter")
            if chapters:
                chapter_queries = []
                for chapter in chapters:
                    if chapter and chapter.strip():
                        chapter_queries.append(Q(participant__user__area_from__unit__chapter__chapter_name__icontains=chapter))
                if chapter_queries:
                    from functools import reduce
                    import operator
                    query_params.append(reduce(operator.or_, chapter_queries))
                
            # Cluster filtering
            clusters = request.query_params.getlist("cluster")
            if clusters:
                cluster_queries = []
                for cluster in clusters:
                    if cluster and cluster.strip():
                        cluster_queries.append(Q(participant__user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster))
                if cluster_queries:
                    from functools import reduce
                    import operator
                    query_params.append(reduce(operator.or_, cluster_queries))
            
            # Status filter (for participant questions)
            status_filter = request.query_params.get("question_status")
            if status_filter:
                status_upper = status_filter.upper()
                if status_upper in ['PENDING', 'ANSWERED', 'CLOSED']:
                    query_params.append(Q(status__iexact=status_upper))
            
            # Priority filter
            priority = request.query_params.get("priority")
            if priority:
                priority_upper = priority.upper()
                if priority_upper in ['LOW', 'MEDIUM', 'HIGH']:
                    query_params.append(Q(priority__iexact=priority_upper))
            
            # Question type filter
            question_type = request.query_params.get("questions_type")
            if question_type:
                type_upper = question_type.upper()
                if type_upper in ['GENERAL', 'CHANGE_REQUEST', 'OTHER']:
                    query_params.append(Q(questions_type__iexact=type_upper))
            
            # Participant status filter (to match participant filtering)
            participant_status = request.query_params.get("status")
            if participant_status:
                status_upper = participant_status.upper()
                if status_upper in ['REGISTERED', 'CONFIRMED', 'CANCELLED']:
                    query_params.append(Q(participant__status__iexact=status_upper))
            
            # Base queryset with optimized joins
            questions = ParticipantQuestion.objects.filter(event=event).select_related(
                'participant', 
                'participant__user', 
                'participant__user__area_from',
                'answered_by'
            ).prefetch_related(
                'participant__user__area_from__unit__chapter__cluster'
            )
            
            # Apply filters
            if query_params:
                from functools import reduce
                import operator
                questions = questions.filter(reduce(operator.and_, query_params))
            
            # Order by most recent first
            questions = questions.order_by('-submitted_at')
            
            # Pagination
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 25))
            
            from django.core.paginator import Paginator
            paginator = Paginator(questions, page_size)
            page_obj = paginator.get_page(page)
            
            # Serialize with enhanced details
            serializer = ParticipantQuestionSerializer(page_obj.object_list, many=True)
            
            # Enhance with participant details
            enhanced_data = []
            for question_data in serializer.data:
                question_obj = questions.get(id=question_data['id'])
                participant = question_obj.participant
                
                enhanced_data.append({
                    **question_data,
                    'participant_details': {
                        'event_pax_id': participant.event_pax_id,
                        'participant_name': participant.user.get_full_name(),
                        'participant_email': participant.user.primary_email,
                        'participant_type': participant.participant_type,
                        'participant_status': participant.status
                    },
                    'event_name': event.name
                })
            
            return Response({
                'questions_asked': enhanced_data,
                'pagination': {
                    'current_page': page,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'page_size': page_size,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            })
            
        except Exception as e:
            print(f"❌ Error getting questions asked: {e}")
            import traceback
            traceback.print_exc()
            return Response({
                'questions_asked': [],
                'pagination': {
                    'current_page': 1,
                    'total_pages': 0,
                    'total_count': 0,
                    'page_size': 25
                },
                'error': str(e)
            }, status=500)
    
    @action(detail=True, methods=['post'], url_name="approve", url_path="approve")
    def approve_event(self, request, id=None):
        """
        Approve an event - only Event Approvers or Community Admins can do this
        Approvers can only approve events for organisations they have access to
        """
        event = self.get_object()
        user = request.user
        
        # Check if user has Event Approver or Community Admin role
        from apps.users.models import UserCommunityRole, CommunityRole
        
        user_roles = UserCommunityRole.objects.filter(user=user).select_related('role').prefetch_related('allowed_organisation_control')
        
        has_approval_permission = False
        allowed_orgs = []
        
        for user_role in user_roles:
            role_name = user_role.role.get_role_name_display()
            if role_name in ['Event Approver', 'Community Admin']:
                has_approval_permission = True
                # Get all organisations this user can approve for
                user_orgs = list(user_role.allowed_organisation_control.all())
                allowed_orgs.extend(user_orgs)
        
        if not has_approval_permission:
            return Response(
                {'error': 'You do not have permission to approve events'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event's organisation is in user's allowed organisations
        if event.organisation and event.organisation not in allowed_orgs:
            return Response(
                {'error': 'You can only approve events for organisations you manage'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event is already approved
        if event.approved:
            return Response(
                {'message': 'Event is already approved'},
                status=status.HTTP_200_OK
            )
        
        # Approve the event
        approval_notes = request.data.get('approval_notes', '')
        
        event.approved = True
        event.approved_by = user
        event.approved_at = timezone.now()
        event.approval_notes = approval_notes
        event.rejected = False
        event.rejection_reason = ''
        event.save()
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event approved successfully',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name="reject", url_path="reject")
    def reject_event(self, request, id=None):
        """
        Reject an event - only Event Approvers or Community Admins can do this
        Rejecting an event sets status to REJECTED
        """
        event = self.get_object()
        user = request.user
        
        # Check if user has Event Approver or Community Admin role
        from apps.users.models import UserCommunityRole, CommunityRole
        
        user_roles = UserCommunityRole.objects.filter(user=user).select_related('role').prefetch_related('allowed_organisation_control')
        
        has_approval_permission = False
        allowed_orgs = []
        
        for user_role in user_roles:
            role_name = user_role.role.get_role_name_display()
            if role_name in ['Event Approver', 'Community Admin']:
                has_approval_permission = True
                # Get all organisations this user can approve for
                user_orgs = list(user_role.allowed_organisation_control.all())
                allowed_orgs.extend(user_orgs)
        
        if not has_approval_permission:
            return Response(
                {'error': 'You do not have permission to reject events'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event's organisation is in user's allowed organisations
        if event.organisation and event.organisation not in allowed_orgs:
            return Response(
                {'error': 'You can only reject events for organisations you manage'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Reject the event
        rejection_reason = request.data.get('rejection_reason', '')
        
        if not rejection_reason:
            return Response(
                {'error': 'rejection_reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        event.rejected = True
        event.rejection_reason = rejection_reason
        event.approved = False
        event.approved_by = None
        event.approved_at = None
        event.approval_notes = ''
        event.status = Event.EventStatus.REJECTED
        event.is_public = False
        event.registration_open = False
        event.save()
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event rejected and cancelled successfully',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name="unapprove", url_path="unapprove")
    def unapprove_event(self, request, id=None):
        """
        Unapprove an event - only Event Approvers or Community Admins can do this
        Unapproving forces status to CANCELLED
        """
        event = self.get_object()
        user = request.user
        
        # Check if user has Event Approver or Community Admin role
        from apps.users.models import UserCommunityRole, CommunityRole
        
        user_roles = UserCommunityRole.objects.filter(user=user).select_related('role').prefetch_related('allowed_organisation_control')
        
        has_approval_permission = False
        allowed_orgs = []
        
        for user_role in user_roles:
            role_name = user_role.role.get_role_name_display()
            if role_name in ['Event Approver', 'Community Admin']:
                has_approval_permission = True
                # Get all organisations this user can approve for
                user_orgs = list(user_role.allowed_organisation_control.all())
                allowed_orgs.extend(user_orgs)
        
        if not has_approval_permission:
            return Response(
                {'error': 'You do not have permission to unapprove events'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event's organisation is in user's allowed organisations
        if event.organisation and event.organisation not in allowed_orgs:
            return Response(
                {'error': 'You can only unapprove events for organisations you manage'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event is not approved
        if not event.approved:
            return Response(
                {'message': 'Event is already not approved'},
                status=status.HTTP_200_OK
            )
        
        # Unapprove the event
        unapproval_reason = request.data.get('reason', '')
        
        event.approved = False
        event.approved_by = None
        event.approved_at = None
        event.approval_notes = f"Unapproved by {user.get_full_name()}. Reason: {unapproval_reason}"
        event.status = Event.EventStatus.POSTPONED
        event.is_public = False
        event.registration_open = False
        event.save()
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event unapproved and cancelled successfully',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name="cancel", url_path="cancel")
    def cancel_event_action(self, request, id=None):
        """
        Cancel an event - only event creators, event heads, or CFC coordinators can do this.
        Requires confirmation input matching event name.
        
        Request body:
        - reason: Optional cancellation reason
        - confirmation: Must match event name exactly for confirmation
        """
        event = self.get_object()
        user = request.user
        
        # Check permissions - must have full event access
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to cancel this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event can be cancelled
        can_cancel, reason = event.can_be_cancelled()
        if not can_cancel:
            return Response(
                {'error': reason},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Require confirmation matching event name
        confirmation = request.data.get('confirmation', '').strip()
        if confirmation != event.name:
            return Response(
                {'error': f'Confirmation failed. Please type "{event.name}" exactly to confirm cancellation.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cancel the event
        cancellation_reason = request.data.get('reason', '')
        
        try:
            event.cancel_event(reason=cancellation_reason)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event cancelled successfully',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name="postpone", url_path="postpone")
    def postpone_event_action(self, request, id=None):
        """
        Postpone an event - only event creators, event heads, or CFC coordinators can do this.
        
        Request body:
        - reason: Optional postponement reason
        """
        event = self.get_object()
        user = request.user
        
        # Check permissions - must have full event access
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to postpone this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if event can be postponed
        can_postpone, reason = event.can_be_postponed()
        if not can_postpone:
            return Response(
                {'error': reason},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Postpone the event
        postponement_reason = request.data.get('reason', '')
        
        try:
            event.postpone_event(reason=postponement_reason)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event postponed successfully',
            'event': serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], url_name="check_deletion_safety", url_path="check-deletion-safety")
    def check_deletion_safety(self, request, id=None):
        """
        Check if event can be safely deleted without data loss.
        Returns deletion safety information.
        """
        event = self.get_object()
        user = request.user
        
        # Check permissions - must have full event access
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to check deletion safety for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check deletion safety
        can_delete, reason, has_sensitive_data = event.can_safely_delete()
        
        return Response({
            'can_safely_delete': can_delete,
            'reason': reason,
            'has_sensitive_data': has_sensitive_data,
            'participant_count': event.participants.count(),
            'event_payment_count': event.event_payments.count(),
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_name="request_deletion", url_path="request-deletion")
    def request_deletion(self, request, id=None):
        """
        Request deletion of an event - marks it as PENDING_DELETION.
        Only event creators, event heads, or CFC coordinators can do this.
        Requires confirmation input matching event name.
        
        Request body:
        - confirmation: Must match event name exactly
        - deletion_date: Optional - when to permanently delete (ISO format)
        """
        event: Event = self.get_object()
        user = request.user
        
        # Check permissions - must have full event access
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to request deletion for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Require confirmation matching event name
        confirmation = request.data.get('confirmation', '').strip()
        if confirmation != event.name:
            return Response(
                {'error': f'Confirmation failed. Please type "{event.name}" exactly to confirm deletion request.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if event has sensitive data
        can_delete, reason, has_sensitive_data = event.can_safely_delete()
        
        # Parse deletion date if provided
        deletion_date = None
        if request.data.get('deletion_date'):
            from django.utils.dateparse import parse_datetime
            deletion_date = parse_datetime(request.data.get('deletion_date'))
        
        # Mark for deletion
        try:
            event.mark_for_deletion(deletion_date=deletion_date)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Serialize and return
        serializer = self.get_serializer(event)
        
        return Response({
            'message': 'Event marked for deletion. Community admins will review before permanent deletion.',
            'event': serializer.data,
            'has_sensitive_data': has_sensitive_data,
            'deletion_date': event.date_for_deletion
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], url_name="daily_checkin_status", url_path="live-dashboard/daily-checkin-status")
    def daily_checkin_status(self, request, id=None):
        """
        Get check-in status counts for a specific day.
        
        Status definitions:
        - Signed In: Currently checked in (has attendance record with NULL check_out_time)
        - Not Signed In: Has attendance records for the day but all are checked out
        - Did Not Turn Up: No attendance records for this day at all
        
        Query params:
        - day: Date in ISO format (YYYY-MM-DD) - required
        - cluster: Filter by cluster name (optional)
        - chapter: Filter by chapter name (optional)
        - area: Filter by area name (optional)
        """
        from django.db.models import Count, Q, Case, When, IntegerField
        from datetime import datetime, timedelta
        
        # Get event directly without queryset filters
        event = get_object_or_404(Event, id=id)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_access_live_dashboard'):
            return Response(
                {'error': 'You do not have permission to access live dashboard statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters
        day_param = request.query_params.get('day')
        if not day_param:
            return Response(
                {'error': 'day parameter is required (format: YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            selected_date = datetime.strptime(day_param, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Location filters
        cluster = request.query_params.get('cluster')
        chapter = request.query_params.get('chapter')
        area = request.query_params.get('area')
        
        # Get all participants for this event
        participants = EventParticipant.objects.filter(event=event).select_related(
            'user',
            'user__area_from',
            'user__area_from__unit',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster'
        )
        print("\n CHAPTER IS ", chapter)
        # Apply location filters
        if area:
            participants = participants.filter(user__area_from__area_name__icontains=area)
        elif chapter:
            participants = participants.filter(user__area_from__unit__chapter__chapter_name__icontains=chapter)
        elif cluster:
            participants = participants.filter(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster)
        
        # Get set of participant user IDs for this event (with location filters applied)
        participant_user_ids = set(participants.values_list('user_id', flat=True))
        total_participants = len(participant_user_ids)
        
        # Get attendance records for the specific day
        day_start = datetime.combine(selected_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        
        # Get all attendance records for this day
        day_attendance = EventDayAttendance.objects.filter(
            event=event,
            check_in_time__gte=day_start,
            check_in_time__lt=day_end
        ).select_related('user')
        
        # Build sets of DISTINCT user IDs by status
        # Signed In: Users with at least one attendance record where check_out_time is NULL
        signed_in_user_ids = set()
        # Has Attendance: Users with at least one attendance record for this day
        has_attendance_user_ids = set()
        
        for attendance in day_attendance:
            user_id = attendance.user_id
            # Only count if user is in filtered participant list
            if user_id in participant_user_ids:
                has_attendance_user_ids.add(user_id)
                if attendance.check_out_time is None:
                    signed_in_user_ids.add(user_id)
        
        # Calculate counts
        signed_in_count = len(signed_in_user_ids)
        
        # Not Signed In: Users who have attendance but are NOT currently signed in
        not_signed_in_user_ids = has_attendance_user_ids - signed_in_user_ids
        not_signed_in_count = len(not_signed_in_user_ids)
        
        # Did Not Turn Up: Participants with NO attendance records for this day
        did_not_turn_up_user_ids = participant_user_ids - has_attendance_user_ids
        did_not_turn_up_count = len(did_not_turn_up_user_ids)
        
        result = {
            'date': day_param,
            'total_participants': total_participants,
            'signed_in': signed_in_count,
            'not_signed_in': not_signed_in_count,
            'did_not_turn_up': did_not_turn_up_count,
            'filters': {
                'cluster': cluster,
                'chapter': chapter,
                'area': area
            }
        }
        
        return Response(result)
    
    @action(detail=True, methods=['get'], url_name="outstanding_payments_by_location", url_path="live-dashboard/outstanding-payments")
    def outstanding_payments_by_location(self, request, id=None):
        """
        Get outstanding payments aggregated by location (Area level).
        Supports toggle between amount and count.
        
        Query params:
        - cluster: Filter by cluster (shows all chapters/areas under it)
        - chapter: Filter by chapter (shows all areas under it)
        - area: Filter by specific area
        - metric: 'amount' or 'count' (default: 'amount')
        """
        from django.db.models import Sum, Count, Q
        from decimal import Decimal
        from collections import defaultdict
        
        # Get event directly without queryset filters
        event = get_object_or_404(Event, id=id)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_access_live_dashboard'):
            return Response(
                {'error': 'You do not have permission to access live dashboard statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters
        cluster = request.query_params.get('cluster')
        chapter = request.query_params.get('chapter')
        area = request.query_params.get('area')
        metric = request.query_params.get('metric', 'amount')  # 'amount' or 'count'
        
        # Get participants with their outstanding payments
        participants = EventParticipant.objects.filter(event=event).select_related(
            'user',
            'user__area_from',
            'user__area_from__unit',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster'
        )
        
        # Apply location filters - if chapter selected, show dropdown to select from chapters in that cluster
        if area:
            participants = participants.filter(user__area_from__area_name__icontains=area)
        elif chapter:
            participants = participants.filter(user__area_from__unit__chapter__chapter_name__icontains=chapter)
        elif cluster:
            participants = participants.filter(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster)
        
        # Aggregate by Area
        location_data = defaultdict(lambda: {'area_name': '', 'outstanding_amount': Decimal('0.00'), 'participant_count': 0})
        
        for participant in participants:
            if not participant.user or not participant.user.area_from:
                continue
            
            area_name = participant.user.area_from.area_name
            
            # Calculate outstanding amount for this participant
            # total_cost = participant.total_cost or Decimal('0.00')
            # paid_amount = participant.paid_amount or Decimal('0.00')
            outstanding = participant.total_outstanding
            
            if outstanding > 0:
                location_data[area_name]['area_name'] = area_name
                location_data[area_name]['outstanding_amount'] += outstanding
                location_data[area_name]['participant_count'] += 1
        
        # Convert to list and sort
        data = sorted(
            [v for v in location_data.values()],
            key=lambda x: x['outstanding_amount'] if metric == 'amount' else x['participant_count'],
            reverse=True
        )
        
        result = {
            'metric': metric,
            'data': data,
            'filters': {
                'cluster': cluster,
                'chapter': chapter,
                'area': area
            }
        }
        
        return Response(result)
    
    @action(detail=True, methods=['get'], url_name="attendance_trends", url_path="live-dashboard/attendance-trends")
    def attendance_trends(self, request, id=None):
        """
        Get check-in and check-out trends over time.
        Supports multiple granularities.
        
        Query params:
        - start_date: Start date (ISO format, default: event start)
        - end_date: End date (ISO format, default: event end)
        - granularity: 'hourly', 'daily', or 'event_days' (default: 'daily')
        - cluster: Filter by cluster (optional)
        - chapter: Filter by chapter (optional)
        - area: Filter by area (optional)
        """
        from django.db.models import Count, Q
        from django.db.models.functions import TruncHour, TruncDate
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        # Get event directly without queryset filters
        event = get_object_or_404(Event, id=id)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_access_live_dashboard'):
            return Response(
                {'error': 'You do not have permission to access live dashboard statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters
        granularity = request.query_params.get('granularity', 'daily')
        cluster = request.query_params.get('cluster')
        chapter = request.query_params.get('chapter')
        area = request.query_params.get('area')
        
        # Date range
        start_date_param = request.query_params.get('start_date')
        end_date_param = request.query_params.get('end_date')
        
        if start_date_param:
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid start_date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            start_date = event.start_date.date() if hasattr(event.start_date, 'date') else event.start_date
        
        if end_date_param:
            try:
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid end_date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            end_date = event.end_date.date() if hasattr(event.end_date, 'date') else event.end_date
        
        # Get attendance records
        attendance_records = EventDayAttendance.objects.filter(
            event=event,
            check_in_time__date__gte=start_date,
            check_in_time__date__lte=end_date
        ).select_related(
            'user',
            'user__area_from',
            'user__area_from__unit',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster'
        )
        
        # Apply location filters
        if area:
            attendance_records = attendance_records.filter(user__area_from__area_name__icontains=area)
        elif chapter:
            attendance_records = attendance_records.filter(user__area_from__unit__chapter__chapter_name__icontains=chapter)
        elif cluster:
            attendance_records = attendance_records.filter(user__area_from__unit__chapter__cluster__cluster_id__icontains=cluster)
        
        # Aggregate based on granularity
        trends_data = defaultdict(lambda: {'check_ins': 0, 'check_outs': 0})
        
        if granularity == 'hourly':
            for record in attendance_records:
                hour_key = record.check_in_time.strftime('%Y-%m-%d %H:00')
                trends_data[hour_key]['check_ins'] += 1
                
                if record.check_out_time:
                    checkout_hour_key = record.check_out_time.strftime('%Y-%m-%d %H:00')
                    trends_data[checkout_hour_key]['check_outs'] += 1
        
        elif granularity == 'event_days':
            for record in attendance_records:
                day_index = record.day_index
                if day_index:
                    day_key = f"Day {day_index}"
                    trends_data[day_key]['check_ins'] += 1
                    
                    if record.check_out_time:
                        trends_data[day_key]['check_outs'] += 1
        
        else:  # daily (default)
            for record in attendance_records:
                day_key = record.check_in_time.strftime('%Y-%m-%d')
                trends_data[day_key]['check_ins'] += 1
                
                if record.check_out_time:
                    checkout_day_key = record.check_out_time.strftime('%Y-%m-%d')
                    trends_data[checkout_day_key]['check_outs'] += 1
        
        # Convert to list and sort
        data = [
            {
                'period': k,
                'check_ins': v['check_ins'],
                'check_outs': v['check_outs']
            }
            for k, v in sorted(trends_data.items())
        ]
        
        result = {
            'granularity': granularity,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'data': data,
            'filters': {
                'cluster': cluster,
                'chapter': chapter,
                'area': area
            }
        }
        
        return Response(result)
    
    @action(detail=True, methods=['post'], url_name="admin_delete", url_path="admin-delete")
    def admin_delete_event(self, request, id=None):
        """
        Admin action to delete an event.
        - If event has sensitive data: soft-delete (mark as DELETED status)
        - If event has no sensitive data: hard-delete (remove from database)
        Only Community Admins can do this.
        Requires confirmation input.
        
        Request body:
        - confirmation: Must be "delete <event_name>" exactly
        """
        event = self.get_object()
        user = request.user
        
        # Check if user is Community Admin
        from apps.users.models import UserCommunityRole, CommunityRole
        
        user_roles = UserCommunityRole.objects.filter(user=user).select_related('role')
        
        is_community_admin = any(
            role.role.get_role_name_display() == 'Community Admin' 
            for role in user_roles
        )
        
        if not is_community_admin:
            return Response(
                {'error': 'Only Community Admins can permanently delete events'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Require strict confirmation
        confirmation = request.data.get('confirmation', '').strip()
        expected_confirmation = f"delete {event.name}"
        
        if confirmation != expected_confirmation:
            return Response(
                {'error': f'Confirmation failed. Please type "delete {event.name}" exactly to confirm deletion.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check deletion safety
        can_delete, reason, has_sensitive_data = event.can_safely_delete()
        
        # Store event details for response
        event_name = event.name
        event_id = str(event.id)
        
        try:
            if has_sensitive_data:
                # Soft delete - mark as DELETED status (will be cleaned up later by Django admin)
                event.mark_as_deleted()
                
                return Response({
                    'message': f'Event "{event_name}" has been marked as DELETED. It will be permanently removed from the database after {event.date_for_deletion.strftime("%Y-%m-%d")}.',
                    'event_id': event_id,
                    'event_name': event_name,
                    'deletion_type': 'soft_delete',
                    'has_sensitive_data': True,
                    'reason': reason,
                    'deletion_date': event.date_for_deletion.isoformat() if event.date_for_deletion else None
                }, status=status.HTTP_200_OK)
            else:
                # Hard delete - permanently remove from database
                event.delete()
                
                return Response({
                    'message': f'Event "{event_name}" (ID: {event_id}) has been permanently deleted from the database.',
                    'deleted_event_id': event_id,
                    'deleted_event_name': event_name,
                    'deletion_type': 'hard_delete',
                    'has_sensitive_data': False
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {'error': f'Failed to delete event: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_name="archive", url_path="archive")
    def archive_event(self, request, id=None):
        """
        Archive a completed event.
        - Event must have COMPLETED status to be archived
        - Archived events are hidden from public listings but remain accessible to creator
        - Archived events cannot be managed (read-only access only)
        - Only event creators or users with full event access can archive
        
        Request body:
        - confirmation: Optional confirmation message
        """
        event = self.get_object()
        user = request.user
        
        # Check if user has permission to archive
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to archive this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate event is COMPLETED
        if event.status != Event.EventStatus.COMPLETED:
            return Response(
                {'error': 'Only completed events can be archived. Current status: ' + event.get_status_display()},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if already archived
        if event.status == Event.EventStatus.ARCHIVED:
            return Response(
                {'error': 'This event is already archived'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Update status to ARCHIVED
            event.status = Event.EventStatus.ARCHIVED
            event.save(update_fields=['status'])
            
            # Serialize response
            serializer = self.get_serializer(event)
            
            return Response({
                'message': f'Event "{event.name}" has been successfully archived.',
                'event': serializer.data,
                'status': 'ARCHIVED'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to archive event: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_name="unarchive", url_path="unarchive")
    def unarchive_event(self, request, id=None):
        """
        Unarchive an archived event and set it back to COMPLETED with public=False.
        - Event must have ARCHIVED status to be unarchived
        - Sets status to COMPLETED and is_public to False
        - Only event creators or users with full event access can unarchive
        
        Request body:
        - confirmation: Optional confirmation message
        """
        event = self.get_object()
        user = request.user
        
        # Check if user has permission to unarchive
        if not has_full_event_access(user, event):
            return Response(
                {'error': 'You do not have permission to unarchive this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate event is ARCHIVED
        if event.status != Event.EventStatus.ARCHIVED:
            return Response(
                {'error': 'Only archived events can be unarchived. Current status: ' + event.get_status_display()},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Update status to COMPLETED and set public to False
            event.status = Event.EventStatus.COMPLETED
            event.is_public = False
            event.save(update_fields=['status', 'is_public'])
            
            # Serialize response
            serializer = self.get_serializer(event)
            
            return Response({
                'message': f'Event "{event.name}" has been successfully unarchived and set to COMPLETED (private).',
                'event': serializer.data,
                'status': 'COMPLETED',
                'is_public': False
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to unarchive event: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_name="admin_events", url_path="admin-events")
    def admin_events(self, request):
        """
        Get all events for admin dashboard - filtered by user's allowed organisations
        Only Event Approvers and Community Admins can access this
        
        Query params:
        - approval_status: 'pending', 'approved', 'rejected', or 'all' (default: 'all')
        - organisation: filter by organisation ID
        - search: search by event name or code
        """
        user = request.user
        
        # Check if user has Event Approver or Community Admin role
        from apps.users.models import UserCommunityRole
        
        user_roles = UserCommunityRole.objects.filter(user=user).select_related('role').prefetch_related('allowed_organisation_control')
        
        has_approval_permission = False
        allowed_org_ids = []
        
        for user_role in user_roles:
            role_name = user_role.role.get_role_name_display()
            if role_name in ['Event Approver', 'Community Admin']:
                has_approval_permission = True
                # Get all organisation IDs this user can approve for
                user_org_ids = list(user_role.allowed_organisation_control.values_list('id', flat=True))
                allowed_org_ids.extend(user_org_ids)
        
        if not has_approval_permission:
            return Response(
                {'error': 'You do not have permission to access admin events'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Build base queryset - all events user can access
        base_queryset = Event.objects.exclude(status=Event.EventStatus.DELETED)
        
        # Filter by allowed organisations (including events with no organisation)
        if allowed_org_ids:
            base_queryset = base_queryset.filter(
                Q(organisation__id__in=allowed_org_ids) | Q(organisation__isnull=True)
            )
        
        # Calculate statistics on BASE queryset (before other filters)
        stats = {
            'total_events': base_queryset.count(),
            'pending_approval': base_queryset.filter(
                approved=False, 
                rejected=False, 
                status__in=[Event.EventStatus.PLANNING, Event.EventStatus.CONFIRMED]
            ).exclude(
                status__in=[Event.EventStatus.CANCELLED, Event.EventStatus.REJECTED, Event.EventStatus.PENDING_DELETION, Event.EventStatus.DELETED]
            ).count(),
            'approved': base_queryset.filter(approved=True, rejected=False).count(),
            'rejected': base_queryset.filter(rejected=True, status=Event.EventStatus.REJECTED).count(),
            'cancelled': base_queryset.filter(status=Event.EventStatus.CANCELLED, rejected=False).count(),
            'postponed': base_queryset.filter(status=Event.EventStatus.POSTPONED).count(),
            'pending_deletion': base_queryset.filter(status=Event.EventStatus.PENDING_DELETION).count(),
        }
        
        # Now apply additional filters for display
        queryset = base_queryset
        
        # Filter by approval status
        approval_status = request.query_params.get('approval_status', 'all')
        if approval_status == 'pending':
            queryset = queryset.filter(approved=False, rejected=False)
        elif approval_status == 'approved':
            queryset = queryset.filter(approved=True)
        elif approval_status == 'rejected':
            queryset = queryset.filter(rejected=True)
        
        # Filter by specific organisation
        org_filter = request.query_params.get('organisation')
        if org_filter:
            queryset = queryset.filter(organisation__id=org_filter)
        
        # Filter by area
        area_filter = request.query_params.get('area')
        if area_filter:
            queryset = queryset.filter(areas_involved__id=area_filter)
        
        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(event_code__icontains=search)
            )
        
        # Order by start date (newest first)
        queryset = queryset.order_by('-start_date')
        
        # Serialize
        serializer = UserAwareEventSerializer(queryset, many=True, context={'request': request})
        
        # Get all areas from allowed organisations for filtering
        from apps.events.models import AreaLocation
        allowed_areas = AreaLocation.objects.filter(
            unit__chapter__cluster__world_location__country='GB'  # Adjust based on your needs
        ).values('id', 'area_name').distinct()
        
        return Response({
            'events': serializer.data,
            'statistics': stats,
            'allowed_organisations': [str(org_id) for org_id in set(allowed_org_ids)],
            'allowed_areas': list(allowed_areas)
        }, status=status.HTTP_200_OK)

    # ==================== REGISTRATION SANITY CHECK ENDPOINTS ====================
    
    @action(detail=True, methods=['post'], url_path='registration/sanity-check')
    def registration_sanity_check(self, request, id=None):
        """
        Sanity check endpoint for registration validation.
        
        Query params:
            step: 'personal' | 'safeguarding' | 'area'
        
        POST body varies by step.
        
        Returns:
            {
                "valid": true/false,
                "errors": {...},  # Blocking errors
                "warnings": {...}  # Non-blocking warnings
            }
        """
        step = request.query_params.get('step')
        
        if not step:
            return Response(
                {'error': 'Step parameter required (personal, safeguarding, or area)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        event = self.get_object()
        
        # Route to appropriate validation function
        if step == 'personal':
            return self._validate_personal_step(request, event)
        elif step == 'safeguarding':
            return self._validate_safeguarding_step(request, event)
        elif step == 'area':
            return self._validate_area_step(request, event)
        else:
            return Response(
                {'error': f'Invalid step: {step}. Must be personal, safeguarding, or area'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'], url_path='registration/emergency-contact-relationships')
    def get_emergency_contact_relationships(self, request):
        """
        Get list of available emergency contact relationship types.
        
        Returns:
            [
                {"value": "MOTHER", "label": "Mother"},
                {"value": "FATHER", "label": "Father"},
                ...
            ]
        """
        relationships = [
            {'value': choice[0], 'label': choice[1]}
            for choice in EmergencyContact.ContactRelationshipType.choices
        ]
        
        return Response(relationships)
    
    # Helper methods for sanity checks
    
    def _validate_phone_number(self, phone):
        """Validate UK/international phone number format."""
        if not phone:
            return False
        
        # Remove spaces, hyphens, parentheses
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        
        # Check for valid patterns
        patterns = [
            r'^(\+44|0044|0)\d{10}$',  # UK
            r'^\+\d{10,14}$',  # International
            r'^\d{10,11}$'  # Simple 10-11 digit number
        ]
        
        return any(re.match(pattern, cleaned) for pattern in patterns)
    
    def _calculate_age(self, dob):
        """Calculate age from date of birth."""
        if isinstance(dob, str):
            try:
                from datetime import datetime
                dob = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError:
                return None
        
        if not isinstance(dob, date):
            return None
        
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    
    def _name_similarity(self, name1, name2):
        """Calculate similarity ratio between two names."""
        if not name1 or not name2:
            return 0.0
        
        name1_clean = name1.lower().strip()
        name2_clean = name2.lower().strip()
        
        return SequenceMatcher(None, name1_clean, name2_clean).ratio()
    
    def _validate_external_id(self, external_id, event):
        """Validate external/secondary reference ID."""
        errors = {}
        
        if not external_id:
            return errors
        
        # Check format
        if not re.match(r'^[A-Za-z0-9\-_]{3,50}$', external_id):
            errors['external_id'] = 'External ID must be 3-50 characters (letters, numbers, hyphens, underscores only)'
            return errors
        
        # Check uniqueness
        existing = EventParticipant.objects.filter(
            event=event,
            secondary_reference_id=external_id
        ).exists()
        
        if existing:
            errors['external_id'] = 'This external ID is already registered for this event'
        
        return errors
    
    def _validate_date_of_birth(self, dob_str):
        """Validate date of birth."""
        errors = {}
        
        if not dob_str:
            errors['date_of_birth'] = 'Date of birth is required'
            return errors
        
        try:
            from datetime import datetime
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            errors['date_of_birth'] = 'Invalid date format. Use YYYY-MM-DD'
            return errors
        
        if dob > date.today():
            errors['date_of_birth'] = 'Date of birth cannot be in the future'
            return errors
        
        age = self._calculate_age(dob)
        if age and age > 120:
            errors['date_of_birth'] = 'Invalid date of birth (age exceeds 120 years)'
        elif age and age < 0:
            errors['date_of_birth'] = 'Invalid date of birth'
        
        return errors
    
    def _check_email_uniqueness(self, email, user_id=None):
        """Check if email is already registered to another user."""
        if not email:
            return None
        
        User = get_user_model()
        
        # Check primary email
        query = User.objects.filter(primary_email=email)
        if user_id:
            query = query.exclude(id=user_id)
        
        existing_user = query.first()
        if existing_user:
            return f'Email already registered to {existing_user.get_full_name()} ({existing_user.member_id})'
        
        # Check secondary email
        query = User.objects.filter(secondary_email=email)
        if user_id:
            query = query.exclude(id=user_id)
        
        existing_user = query.first()
        if existing_user:
            return f'Email already registered as secondary email for {existing_user.get_full_name()} ({existing_user.member_id})'
        
        return None
    
    def _check_name_similarity(self, first_name, last_name, user_id=None):
        """Check for similar names in the database."""
        if not first_name or not last_name:
            return []
        
        User = get_user_model()
        warnings = []
        threshold = 0.85  # 85% similarity threshold
        
        query = User.objects.all()
        if user_id:
            query = query.exclude(id=user_id)
        
        for user in query:
            first_similarity = self._name_similarity(first_name, user.first_name)
            last_similarity = self._name_similarity(last_name, user.last_name)
            
            if first_similarity >= threshold and last_similarity >= threshold:
                warnings.append(
                    f'Similar name found: {user.get_full_name()} ({user.primary_email or user.member_id})'
                )
        
        return warnings
    
    def _validate_personal_step(self, request, event):
        """Validate personal information step."""
        data = request.data
        errors = {}
        warnings = {}
        
        user_id = request.user.id if request.user.is_authenticated else None
        
        # Validate external ID
        external_id = data.get('external_id')
        if external_id:
            ext_errors = self._validate_external_id(external_id, event)
            errors.update(ext_errors)
        
        # Validate date of birth
        dob = data.get('date_of_birth')
        dob_errors = self._validate_date_of_birth(dob)
        errors.update(dob_errors)
        
        # Validate phone number
        phone = data.get('phone_number')
        if not phone:
            errors['phone_number'] = 'Phone number is required'
        elif not self._validate_phone_number(phone):
            errors['phone_number'] = 'Invalid phone number format'
        
        # Validate email
        email = data.get('email')
        if not email:
            errors['email'] = 'Email is required'
        else:
            try:
                django_validate_email(email)
            except ValidationError:
                errors['email'] = 'Invalid email format'
            
            # Check uniqueness (warning only)
            email_warning = self._check_email_uniqueness(email, user_id)
            if email_warning:
                warnings['email'] = email_warning
        
        # Validate names
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        
        if not first_name:
            errors['first_name'] = 'First name is required'
        if not last_name:
            errors['last_name'] = 'Last name is required'
        
        # Check name similarity (warnings only)
        if first_name and last_name:
            name_warnings = self._check_name_similarity(first_name, last_name, user_id)
            if name_warnings:
                warnings['name_similarity'] = name_warnings
        
        return Response({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        })
    
    def _validate_safeguarding_step(self, request, event):
        """Validate safeguarding information step."""
        data = request.data
        errors = {}
        warnings = {}
        
        # Calculate age
        age = None
        dob = data.get('date_of_birth')
        if dob:
            age = self._calculate_age(dob)
        elif data.get('age'):
            age = int(data.get('age'))
        
        if age is None:
            errors['age'] = 'Unable to determine age. Please provide date of birth or age.'
            return Response({
                'valid': False,
                'errors': errors,
                'warnings': warnings
            })
        
        # If under 18, require at least one emergency contact detail
        if age < 18:
            ec_first = data.get('emergency_contact_first_name')
            ec_last = data.get('emergency_contact_last_name')
            ec_relationship = data.get('emergency_contact_relationship')
            ec_phone = data.get('emergency_contact_phone')
            ec_email = data.get('emergency_contact_email')
            
            has_any_contact = any([ec_first, ec_last, ec_phone, ec_email])
            
            if not has_any_contact:
                errors['emergency_contact'] = 'At least one emergency contact detail is required for participants under 18'
            else:
                # Validate individual fields if provided
                if ec_first and len(ec_first.strip()) < 2:
                    errors['emergency_contact_first_name'] = 'First name must be at least 2 characters'
                
                if ec_last and len(ec_last.strip()) < 2:
                    errors['emergency_contact_last_name'] = 'Last name must be at least 2 characters'
                
                if ec_phone and not self._validate_phone_number(ec_phone):
                    errors['emergency_contact_phone'] = 'Invalid phone number format'
                
                if ec_email:
                    try:
                        django_validate_email(ec_email)
                    except ValidationError:
                        errors['emergency_contact_email'] = 'Invalid email format'
                
                # Validate relationship
                if ec_relationship:
                    valid_relationships = [choice[0] for choice in EmergencyContact.ContactRelationshipType.choices]
                    if ec_relationship not in valid_relationships:
                        errors['emergency_contact_relationship'] = f'Invalid relationship type. Must be one of: {", ".join(valid_relationships)}'
        
        return Response({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'age': age,
            'requires_emergency_contact': age < 18
        })
    
    def _validate_area_step(self, request, event):
        """Validate area selection step."""
        data = request.data
        errors = {}
        warnings = {}
        
        area_id = data.get('area_id')
        
        if not area_id:
            errors['area_id'] = 'Area selection is required'
        else:
            try:
                area = AreaLocation.objects.get(area_name=area_id)
            except AreaLocation.DoesNotExist:
                errors['area_id'] = 'Selected area does not exist'
        
        # Get suggested area from user profile
        suggested_area = None
        if request.user.is_authenticated and hasattr(request.user, 'area_from') and request.user.area_from:
            suggested_area = {
                'id': str(request.user.area_from.id),
                'name': request.user.area_from.area_name,
                'chapter': request.user.area_from.unit.chapter.chapter_name if request.user.area_from.unit.chapter else None
            }
        
        return Response({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'suggested_area': suggested_area
        })

        

class EventServiceTeamMemberViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event service team members.
    '''
    queryset = EventServiceTeamMember.objects.all()
    serializer_class = EventServiceTeamMemberSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'head_of_role']

class EventRoleViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event roles.
    '''
    queryset = EventRole.objects.all()
    serializer_class = EventRoleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['role_name', 'description']

class EventParticipantViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event participants.
    Different from users/api/views.py -> CommunityUserViewSet -> events action
    '''
    queryset = EventParticipant.objects.all()
    serializer_class = EventParticipantSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['event', 'user', 'status', 'participant_type']
    search_fields = ['user__first_name', 'user__last_name', 'team_assignment']
    lookup_field = "event_pax_id"
    
    def get_serializer_class(self):
        """
        Use optimized serializer for list views to reduce response size by 70-80%
        Use full serializer for create/update operations that need complete data
        """
        if self.action == 'list':
            return ParticipantManagementSerializer
        elif self.action in ['retrieve'] and self.request.query_params.get('summary', 'false').lower() == 'true':
            return ParticipantManagementSerializer
        return EventParticipantSerializer
        
    @action(detail=False, methods=['post'], url_name="register", url_path="register")
    def register(self, request):
        '''
        {"user": uuid, "event": uuid, "participant_type": "PARTICIPANT"}
        Allow any to register for an event as a participant mainly. Service team registration should be handled separately.
        '''
        user = request.user
        event_id = request.data.get('event_id')
        participant_type = request.data.get('participant_type', EventParticipant.ParticipantType.PARTICIPANT)
        
        if not event_id:
            return Response(
                {'error': _('Event ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response(
                {'error': _('Event not found.')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if EventParticipant.objects.filter(event=event, user=user).exists():
            return Response(
                {'error': _('You are already registered for this event.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if participant_type not in dict(EventParticipant.ParticipantType.choices):
            return Response(
                {'error': _('Invalid participant type.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        if participant_type == EventParticipant.ParticipantType.SERVICE_TEAM and not user.has_perm('events.add_eventserviceteammember'):
            return Response(
                {'error': _('Service team registration is not allowed via this endpoint.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        participant = EventParticipant.objects.create(
            event=event,
            user=user,
            status=EventParticipant.ParticipantStatus.REGISTERED,
            participant_type=participant_type
        )
        
        serializer = self.get_serializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    #TODO: add role to a service team member AND NOT a participant - low priority
    #TODO: cancel booking        
    
    @action(detail=True, methods=['post'], url_name="check-in", url_path="check-in")
    def check_in(self, request, event_pax_id=None):
        '''
        Check in a participant to the event. Returns {participant: date, is_checked_in: bool}
        '''
        # TODO: ensure only service team are allowed to check in
        data = request.data
        
        try:
            event_uuid = data.get("event_uuid")
            event_uuid = uuid.UUID(event_uuid)
        except (ValueError, TypeError):
            raise serializers.ValidationError({"error": "invalid or missing event UUID"})
        
        participant = get_object_or_404(
            EventParticipant,
            Q(event_pax_id = event_pax_id) | Q(secondary_reference_id = event_pax_id),
            event=event_uuid
        )
        
        event: Event = participant.event   
        check_in_datetime_utc = timezone.now()
        
        # Convert to London time for storage
        import pytz
        london_tz = pytz.timezone('Europe/London')
        check_in_datetime = check_in_datetime_utc.astimezone(london_tz)

        if check_in_datetime_utc < event.start_date:
            raise serializers.ValidationError("cannot check in participant as the event has not yet started")
        
        if participant.status != EventParticipant.ParticipantStatus.ATTENDED:
            participant.status = EventParticipant.ParticipantStatus.ATTENDED
            participant.attended_date = timezone.now()
            participant.save()
        
        is_checked_in = EventDayAttendance.objects.filter(
            event=participant.event, 
            user=participant.user,
            check_in_time__date=check_in_datetime.date(),
            check_out_time=None,
        ).exists()
        if not is_checked_in:
            EventDayAttendance.objects.create(
                event=participant.event,
                user=participant.user,
                check_in_time=check_in_datetime,
            )
            
            # Broadcast WebSocket update for check-in
            try:
                print(f"🔔 CHECK-IN API - Starting WebSocket notification for participant: {participant.user.first_name} {participant.user.last_name}")
                print(f"🔔 CHECK-IN API - Event: {participant.event.name} (ID: {participant.event.id})")
                
                participant_data = serialize_participant_for_websocket(participant)
                print(f"📊 CHECK-IN API - Serialized participant data for: {participant_data.get('user', {}).get('first_name', 'Unknown')}")
                print(f"📊 CHECK-IN API - Checked in status: {participant_data.get('checked_in', False)}")
                
                websocket_notifier.notify_checkin_update(
                    event_id=str(participant.event.id),
                    participant_data=participant_data,
                    action='checkin',
                    source='automatic'  # Silent update for other clients; calling client handles its own notification
                )
                
                # Notify dashboard users about participant count change
                supervisor_ids = get_event_supervisors(participant.event)
                websocket_notifier.notify_event_update(
                    user_ids=supervisor_ids,
                    event_id=str(participant.event.id),
                    update_type='participant_checked_in',
                    data={'participant_id': str(participant.id)}
                )
                print(f"✅ CHECK-IN API - WebSocket notification sent successfully!")
                
            except Exception as e:
                # Log the error but don't fail the check-in process
                print(f"❌ CHECK-IN API - WebSocket notification error: {e}")
                import traceback
                print(f"❌ CHECK-IN API - Full traceback: {traceback.format_exc()}")
            
        serializer = ParticipantManagementSerializer(participant)
        return Response({
            "participant": serializer.data,
            "already_checked_in": is_checked_in
        })
    
    @action(detail=True, methods=['post'], url_name="check-out", url_path="check-out")
    def check_out(self, request, event_pax_id=None):
        '''
        Check out a participant from the event.
        '''
        # TODO: ensure only service team are allowed to check in
        data = request.data
        try:
            event_uuid = data.get("event_uuid")
            event_uuid = uuid.UUID(event_uuid)
        except (ValueError, TypeError):
            raise serializers.ValidationError({"error": "invalid or missing event UUID"})

        participant = get_object_or_404(
            EventParticipant,
            Q(event_pax_id = event_pax_id) | Q(secondary_reference_id = event_pax_id),
            event=event_uuid
        )
        check_out_datetime_utc = timezone.now()
        
        # Convert to London time for storage
        import pytz
        london_tz = pytz.timezone('Europe/London')
        check_out_datetime = check_out_datetime_utc.astimezone(london_tz)
                
        checked_in = EventDayAttendance.objects.filter(
            event=participant.event, 
            user=participant.user,
            check_in_time__date=check_out_datetime.date(),
            check_out_time=None
        )
        if checked_in.exists():
            first = checked_in.first()
            first.check_out_time = check_out_datetime
            first.save()
            
            # Broadcast WebSocket update for check-out
            try:
                print(f"🔔 CHECK-OUT API - Starting WebSocket notification for participant: {participant.user.first_name} {participant.user.last_name}")
                print(f"🔔 CHECK-OUT API - Event: {participant.event.name} (ID: {participant.event.id})")
                
                participant_data = serialize_participant_for_websocket(participant)
                print(f"📊 CHECK-OUT API - Serialized participant data for: {participant_data.get('user', {}).get('first_name', 'Unknown')}")
                print(f"📊 CHECK-OUT API - Checked in status: {participant_data.get('checked_in', False)}")
                
                websocket_notifier.notify_checkin_update(
                    event_id=str(participant.event.id),
                    participant_data=participant_data,
                    action='checkout',
                    source='automatic'  # Silent update for other clients; calling client handles its own notification
                )
                
                # Notify dashboard users about participant count change
                supervisor_ids = get_event_supervisors(participant.event)
                websocket_notifier.notify_event_update(
                    user_ids=supervisor_ids,
                    event_id=str(participant.event.id),
                    update_type='participant_checked_out',
                    data={'participant_id': str(participant.id)}
                )
                print(f"✅ CHECK-OUT API - WebSocket notification sent successfully!")
                
            except Exception as e:
                # Log the error but don't fail the check-out process
                print(f"❌ CHECK-OUT API - WebSocket notification error: {e}")
                import traceback
                print(f"❌ CHECK-OUT API - Full traceback: {traceback.format_exc()}")
        else:
            raise serializers.ValidationError("cannot checkout this user as they are not checked in")
        
        serializer = ParticipantManagementSerializer(participant)
        return Response(serializer.data)
        
    def create(self, request, *args, **kwargs):
        """
        Create a new event participant registration.
        
        Supports two payment flows:
        1. Stripe: Returns stripe_client_secret for frontend payment completion
        2. Other methods: Creates payment record in PENDING state
        
        Expected payload includes optional donation_amount for combined payment.
        """
        # First, create the participant using parent serializer
        response = super().create(request, *args, **kwargs)
        data = response.data
        
        try:
            # Get the created participant
            event_user_id = data.get("event_user_id")
            if not event_user_id:
                return Response(response.data, status=response.status_code)
            
            participant = EventParticipant.objects.get(event_pax_id=event_user_id)
            
            # Check if there are any event payments created
            event_payments = data.get('event_payments', [])
            if not event_payments:
                # No payment required, just send confirmation
                from threading import Thread
                email_thread = Thread(target=send_booking_confirmation_email, args=(participant,))
                email_thread.start()
                print(f"📧 Booking confirmation email queued for {event_user_id}")
                
                return Response({
                    "event_user_id": data["event_user_id"],
                    "is_paid": False,
                    "payment_method": None,
                    "needs_verification": False
                }, status=response.status_code)
            
            # Get the first event payment (should only be one during registration)
            event_payment = EventPayment.objects.filter(user=participant).first()
            
            if not event_payment:
                # Send standard confirmation email
                from threading import Thread
                email_thread = Thread(target=send_booking_confirmation_email, args=(participant,))
                email_thread.start()
                print(f"📧 Booking confirmation email queued for {event_user_id}")
                
                return Response({
                    "event_user_id": data["event_user_id"],
                    "is_paid": False,
                    "payment_method": None,
                    "needs_verification": False
                }, status=response.status_code)
            
            # Handle optional donation
            donation_payment = None
            donation_amount = request.data.get('donation_amount')
            
            if donation_amount and float(donation_amount) > 0:
                # Create donation payment with same method as event payment
                donation_payment = DonationPayment.objects.create(
                    user=participant,
                    event=participant.event,
                    method=event_payment.method,
                    amount=float(donation_amount),
                    currency=event_payment.currency,
                    status=DonationPayment.PaymentStatus.PENDING,
                    pay_to_event=request.data.get('pay_to_event', True)
                )
                print(f"💝 Donation payment created: £{donation_amount} for {event_user_id}")
            
            # Check if payment method is Stripe
            payment_method = event_payment.method
            stripe_client_secret = None
            
            if payment_method and payment_method.method == 'STRIPE':
                # Create Stripe PaymentIntent
                from apps.shop.stripe_service import StripePaymentService
                
                try:
                    stripe_service = StripePaymentService()
                    payment_intent = stripe_service.create_event_payment_intent(
                        event_payment=event_payment,
                        donation_payment=donation_payment,
                        metadata={
                            'participant_name': f"{participant.user.first_name} {participant.user.last_name}",
                            'participant_email': participant.user.primary_email,
                        }
                    )
                    
                    if payment_intent:
                        stripe_client_secret = payment_intent['client_secret']
                        print(f"💳 Stripe PaymentIntent created for {event_user_id}: {payment_intent['id']}")
                    else:
                        raise Exception("Failed to create Stripe PaymentIntent")
                        
                except Exception as e:
                    print(f"⚠️ Stripe PaymentIntent creation failed: {e}")
                    # Clean up participant if Stripe fails
                    participant.delete()
                    if donation_payment:
                        donation_payment.delete()
                    return Response(
                        {"error": f"Failed to initialize payment: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # Return response with stripe_client_secret for frontend
                return Response({
                    "event_user_id": data["event_user_id"],
                    "participant_id": str(participant.id),
                    "is_paid": False,
                    "payment_method": payment_method.get_method_display(),
                    "needs_verification": False,
                    "requires_payment_completion": True,
                    "payment": {
                        "stripe_client_secret": stripe_client_secret,
                        "event_payment_id": event_payment.id,
                        "donation_payment_id": str(donation_payment.id) if donation_payment else None,
                        "event_payment_tracking": event_payment.event_payment_tracking_number,
                        "donation_tracking": donation_payment.event_payment_tracking_number if donation_payment else None,
                        "total_amount": float(event_payment.amount + Decimal(donation_payment.amount if donation_payment else 0)),
                        "event_amount": float(event_payment.amount),
                        "donation_amount": float(donation_payment.amount) if donation_payment else 0,
                        "currency": event_payment.currency,
                        "bank_reference": event_payment.bank_reference,
                    }
                }, status=response.status_code)
            
            else:
                # Non-Stripe payment method - send standard confirmation email
                from threading import Thread
                email_thread = Thread(target=send_booking_confirmation_email, args=(participant,))
                email_thread.start()
                print(f"📧 Booking confirmation email queued for {event_user_id}")
                
                # Get payment instructions
                instructions = payment_method.instructions if payment_method else None
                if payment_method and payment_method.method == 'BANK':
                    bank_instructions = {
                        "account_name": payment_method.account_name,
                        "account_number": payment_method.account_number,
                        "sort_code": payment_method.sort_code,
                        "reference": event_payment.bank_reference,
                        "reference_instruction": payment_method.reference_instruction,
                        "important_information": payment_method.important_information,
                    }
                    instructions = bank_instructions
                
                return Response({
                    "event_user_id": data["event_user_id"],
                    "participant_id": str(participant.id),
                    "is_paid": all(p['status'] == 'SUCCEEDED' for p in event_payments),
                    "payment_method": payment_method.get_method_display() if payment_method else None,
                    "needs_verification": any(not p['verified'] for p in event_payments),
                    "requires_payment_completion": False,
                    "payment": {
                        "event_payment_id": event_payment.id,
                        "donation_payment_id": str(donation_payment.id) if donation_payment else None,
                        "event_payment_tracking": event_payment.event_payment_tracking_number,
                        "donation_tracking": donation_payment.event_payment_tracking_number if donation_payment else None,
                        "total_amount": float(event_payment.amount + (donation_payment.amount if donation_payment else 0)),
                        "event_amount": float(event_payment.amount),
                        "donation_amount": float(donation_payment.amount) if donation_payment else 0,
                        "currency": event_payment.currency,
                        "bank_reference": event_payment.bank_reference,
                        "instructions": instructions,
                    }
                }, status=response.status_code)
                
        except Exception as e:
            # Log error but don't fail the registration completely
            print(f"⚠️ Error processing payment for registration: {e}")
            import traceback
            traceback.print_exc()
            
            # Return basic registration info
            return Response({
                "event_user_id": data.get("event_user_id"),
                "is_paid": False,
                "payment_method": None,
                "needs_verification": True,
                "error": str(e)
            }, status=response.status_code)
        
    @action(detail=True, methods=['post'], url_name="confirm-payment", url_path="confirm-payment")
    def confirm_registration_payment(self, request, event_pax_id=None):
        '''
        Confirm a participant's registration for an event. This must be done if they have paid
        Only event organizers/admins can confirm registrations.
        '''
        # TODO: ensure only organisers can do this
        participant = self.get_object()
        if participant.status != EventParticipant.ParticipantStatus.REGISTERED:
            return Response(
                {'error': _('Only participants with REGISTERED status can be confirmed.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment = get_object_or_404(EventPayment, user=participant)
        
        # Check if already verified
        already_verified = payment.verified
        
        payment.verified = True
        payment.paid_at = timezone.now()
        payment.status = EventPayment.PaymentStatus.SUCCEEDED
        payment.save()
        
        # Send confirmation email in background if newly verified
        if not already_verified:
            def send_email():
                try:
                    send_payment_verification_email(participant)
                    print(f"📧 Registration payment verification email queued for {participant.event_pax_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send payment verification email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()
        
        serializer = self.get_serializer(participant)
        participant.status = EventParticipant.ParticipantStatus.CONFIRMED
        participant.save()
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="verify-registration", url_path="verify-registration")
    def verify_participant_status(self, request, event_pax_id=None):
        '''
        Verify a participant's registration status for an event. 
        '''
        # TODO: ensure only organisers can do this
        participant = self.get_object()
        if participant.status != EventParticipant.ParticipantStatus.REGISTERED:
            return Response(
                {'error': _('Only participants with REGISTERED status can be confirmed.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        participant.status = EventParticipant.ParticipantStatus.CONFIRMED
        participant.save()
        serializer = self.get_serializer(participant)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="confirm-merch-payment", url_path="confirm-merch-payment")
    def confirm_merch_order_payment(self, request, event_pax_id=None):
        '''
        Confirm a participant's merchandise order payment for an event.
        Only event organizers/admins can confirm payments.
        Uses centralized payment completion logic from ProductPayment model.
        '''
        # TODO: ensure only organisers can do this
        data = request.data
        participant = get_object_or_404(EventParticipant, event_pax_id=event_pax_id)
        cart = data.get('cart_id')
        if not cart:
            return Response(
                {'error': _('Cart ID is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        cart_instance = get_object_or_404(EventCart, uuid=cart, user=participant.user)
        if not cart_instance.submitted:
            return Response(
                {'error': _('Cart must be submitted before confirming payment.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        product_payment = get_object_or_404(ProductPayment, cart=cart_instance, user=participant.user)
        
        # Check if already approved (for email logic)
        already_approved = product_payment.approved
        
        # Use centralized payment completion logic
        was_completed = product_payment.complete_payment(log_metadata={
            'source': 'manual_confirmation',
            'confirmed_by': request.user.username if request.user else None,
            'participant_id': participant.event_pax_id
        })
        
        # Send confirmation email in background if newly approved
        if not already_approved and was_completed:
            def send_email():
                try:
                    send_payment_verified_email(cart_instance, product_payment)
                    print(f"📧 Merch order payment verification email queued for order {cart_instance.order_reference_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send merch payment verification email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()

        serializer = self.get_serializer(participant)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_name="create-merch-cart", url_path="create-merch-cart")
    def create_merch_cart(self, request, event_pax_id=None):
        '''
        Create a new merchandise cart for a participant with manual orders.
        Only event organizers/admins can create carts for participants.
        
        Expected payload:
        {
            "user_id": "user-uuid",
            "event_id": "event-uuid", 
            "notes": "Optional cart notes",
            "shipping_address": "Optional shipping address",
            "orders": [
                {
                    "product_uuid": "product-uuid",
                    "product_name": "Product Name",
                    "quantity": 2,
                    "price_at_purchase": 15.00,
                    "size": "LG",
                    "size_id": 154
                }
            ]
        }
        '''
        
        try:
            data = request.data
            participant = self.get_object()
            
            # Validate required fields
            orders_data = data.get('orders', [])
            if not orders_data:
                return Response(
                    {'error': _('At least one order is required.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate each order has required fields
            for i, order_data in enumerate(orders_data):
                required_fields = ['product_uuid', 'quantity', 'price_at_purchase']
                missing_fields = [field for field in required_fields if field not in order_data]
                if missing_fields:
                    return Response(
                        {'error': f'Order {i+1} missing required fields: {", ".join(missing_fields)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create the cart
            cart = EventCart.objects.create(
                user=participant.user,
                event=participant.event,
                notes=data.get('notes', ''),
                shipping_address=data.get('shipping_address', ''),
                total=0,  # Will be calculated below
                active=True,
                submitted=False,
                approved=False
            )
            
            total_amount = 0
            
            # Create orders for each product
            for order_data in orders_data:
                try:
                    # Get the product
                    product = EventProduct.objects.get(
                        uuid=order_data['product_uuid'], 
                        event=participant.event
                    )
                    
                    # Get size if specified
                    size_instance = None
                    if order_data.get('size_id'):
                        size_instance = ProductSize.objects.get(
                            id=order_data['size_id'],
                            product=product
                        )
                    
                    # Validate quantity
                    quantity = int(order_data['quantity'])
                    if quantity <= 0:
                        raise ValueError("Quantity must be greater than 0")
                    
                    if quantity > product.maximum_order_quantity:
                        raise ValueError(f"Quantity exceeds maximum order quantity of {product.maximum_order_quantity}")
                    
                    # Calculate price
                    price_at_purchase = float(order_data['price_at_purchase'])
                    if price_at_purchase < 0:
                        raise ValueError("Price cannot be negative")
                    
                    # Create the order
                    order = EventProductOrder.objects.create(
                        product=product,
                        cart=cart,
                        quantity=quantity,
                        price_at_purchase=price_at_purchase,
                        size=size_instance,
                        uses_size=size_instance is not None,
                        status=EventProductOrder.Status.PENDING
                    )
                    
                    # Add to total
                    total_amount += price_at_purchase * quantity
                    
                except EventProduct.DoesNotExist:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Product with UUID {order_data.get("product_uuid")} not found.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except ProductSize.DoesNotExist:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Size with ID {order_data.get("size_id")} not found for this product.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except (ValueError, KeyError) as e:
                    cart.delete()  # Cleanup
                    return Response(
                        {'error': f'Invalid order data: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Update cart total
            cart.total = total_amount
            cart.save()
            
            # Send email notification in background
            def send_email():
                try:
                    send_cart_created_by_admin_email(cart)
                    print(f"📧 Admin cart creation email queued for cart {cart.order_reference_id}")
                except Exception as e:
                    print(f"⚠️ Failed to send admin cart creation email: {e}")
            
            email_thread = threading.Thread(target=send_email)
            email_thread.start()
            
            # Return cart data
            serializer = EventCartMinimalSerializer(cart)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create cart: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['patch'], url_name="update-merch-order", url_path="update-merch-order/(?P<order_id>[^/.]+)")
    def update_merch_order(self, request, event_pax_id=None, order_id=None):
        '''
        Update an individual merchandise order for a participant.
        Only event organizers/admins can update orders.
        
        Expected payload:
        {
            "product_name": "Updated Product Name",
            "size": "MD",
            "quantity": 3,
            "price_at_purchase": 20.00
        }
        '''
        
        try:
            participant = self.get_object()
            
            # Get the order
            try:
                order = EventProductOrder.objects.get(
                    id=order_id,
                    cart__user=participant.user,
                    cart__event=participant.event
                )
            except EventProductOrder.DoesNotExist:
                return Response(
                    {'error': _('Order not found.')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if cart is already approved (can't modify approved carts)
            if order.cart.approved:
                return Response(
                    {'error': _('Cannot modify orders in approved carts.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            data = request.data
            updated_fields = {}  # Track what changed for email notification
            
            # Update fields if provided
            if 'quantity' in data:
                quantity = int(data['quantity'])
                if quantity <= 0:
                    return Response(
                        {'error': _('Quantity must be greater than 0.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if quantity > order.product.maximum_order_quantity:
                    return Response(
                        {'error': f'Quantity exceeds maximum order quantity of {order.product.maximum_order_quantity}.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if order.quantity != quantity:
                    updated_fields['quantity'] = quantity
                    order.quantity = quantity
            
            if 'price_at_purchase' in data:
                price = float(data['price_at_purchase'])
                if price < 0:
                    return Response(
                        {'error': _('Price cannot be negative.')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if order.price_at_purchase != price:
                    updated_fields['price_at_purchase'] = price
                    order.price_at_purchase = price
            
            # Handle size updates
            if 'size' in data:
                size_value = data['size']
                if size_value:
                    try:
                        size_instance = ProductSize.objects.get(
                            size=size_value,
                            product=order.product
                        )
                        if order.size != size_instance:
                            updated_fields['size'] = size_value
                            order.size = size_instance
                            order.uses_size = True
                    except ProductSize.DoesNotExist:
                        return Response(
                            {'error': f'Size "{size_value}" not available for this product.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    if order.size is not None:
                        updated_fields['size'] = 'None (removed)'
                    order.size = None
                    order.uses_size = False
            
            order.save()
            
            # Recalculate cart total
            cart = order.cart
            cart.total = sum(
                (o.price_at_purchase or 0) * o.quantity 
                for o in cart.orders.all()
            )
            cart.save()
            
            # Send email notification if any changes were made
            if updated_fields:
                def send_email():
                    try:
                        send_order_update_email(cart, order, updated_fields)
                        print(f"📧 Order update email queued for order {order.id} in cart {cart.order_reference_id}")
                    except Exception as e:
                        print(f"⚠️ Failed to send order update email: {e}")
                
                email_thread = threading.Thread(target=send_email)
                email_thread.start()
            
            return Response(
                {'message': _('Order updated successfully.')},
                status=status.HTTP_200_OK
            )
            
        except (ValueError, KeyError) as e:
            return Response(
                {'error': f'Invalid data: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to update order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['patch'], url_name="cancel-merch-order", url_path="cancel-merch-order/(?P<order_id>[^/.]+)")
    def cancel_merch_order(self, request, event_pax_id=None, order_id=None):
        '''
        Cancel an individual merchandise order for a participant.
        Only event organizers/admins can cancel orders.
        '''
        
        try:
            participant = self.get_object()
            
            # Get the order
            try:
                order = EventProductOrder.objects.get(
                    id=order_id,
                    cart__user=participant.user,
                    cart__event=participant.event
                )
            except EventProductOrder.DoesNotExist:
                return Response(
                    {'error': _('Order not found.')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if cart is already approved (can't cancel from approved carts)
            if order.cart.approved:
                return Response(
                    {'error': _('Cannot cancel orders in approved carts.')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update status to cancelled
            order.status = EventProductOrder.Status.CANCELLED
            order.save()
            
            # Recalculate cart total (excluding cancelled orders)
            cart = order.cart
            cart.total = sum(
                (o.price_at_purchase or 0) * o.quantity 
                for o in cart.orders.filter(status__in=[
                    EventProductOrder.Status.PENDING,
                    EventProductOrder.Status.PURCHASED
                ])
            )
            cart.save()
            
            return Response(
                {'message': _('Order cancelled successfully.')},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {'error': f'Failed to cancel order: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['delete'], url_name="remove-participant", url_path="remove-participant")
    def remove_participant_from_event(self, request, event_pax_id=None):
        '''
        Remove a participant from the event by changing their status to CANCELLED.
        Creates a refund record if the participant has made payments.
        Sends an email notification to the participant about the removal.
        
        Expected payload:
        {
            "reason": "Reason for removal",
            "confirmation_name": "Participant Full Name"
        }
        '''
        participant = self.get_object()
        data = request.data
        
        # Validate required fields
        reason = data.get('reason', '').strip()
        confirmation_name = data.get('confirmation_name', '').strip()
        
        if not reason:
            return Response(
                {'error': _('A reason for removal is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not confirmation_name:
            return Response(
                {'error': _('Confirmation name is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate confirmation name matches participant name
        participant_full_name = f"{participant.user.first_name} {participant.user.last_name}"
        if confirmation_name.lower() != participant_full_name.lower():
            return Response(
                {'error': _('Confirmation name does not match participant name.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate payment totals for refund
        from decimal import Decimal
        from apps.events.models import ParticipantRefund
        from apps.shop.models import OrderRefund
        
        # Get all event registration payments
        event_payments = participant.participant_event_payments.all()
        event_payment_total = sum(
            payment.amount for payment in event_payments 
            if payment.status == EventPayment.PaymentStatus.SUCCEEDED
        ) or Decimal('0.00')
        
        # Update event payment status to REFUND_PROCESSING
        if event_payment_total > 0:
            event_payments.filter(status=EventPayment.PaymentStatus.SUCCEEDED).update(
                status=EventPayment.PaymentStatus.REFUND_PROCESSING
            )
        
        # Get all product/merchandise carts for this participant's event
        from apps.shop.models import EventCart
        participant_carts = EventCart.objects.filter(
            user=participant.user,
            event=participant.event,
            cart_status='paid'  # Only refund paid carts
        ).prefetch_related('orders')
        
        # Track total merchandise amount and prepare to create OrderRefunds
        product_payment_total = Decimal('0.00')
        order_refunds_to_create = []
        
        for cart in participant_carts:
            # Get the payment for this cart
            continue
            cart_payment = ProductPayment.objects.filter(
                cart=cart,
                status=ProductPayment.PaymentStatus.SUCCEEDED
            ).first()
            
            if cart_payment:
                # Update payment status to REFUND_PROCESSING
                cart_payment.status = ProductPayment.PaymentStatus.REFUND_PROCESSING
                cart_payment.save()
                
                product_payment_total += cart_payment.amount
                
                # Prepare OrderRefund data (will be created after ParticipantRefund)
                order_refunds_to_create.append({
                    'cart': cart,
                    'payment': cart_payment,
                    'amount': cart_payment.amount
                })
        
        # Calculate total amount
        total_amount = event_payment_total + product_payment_total
        has_payments = total_amount > 0
        
        # Get organizer contact email
        organizer_emails = []
        if participant.event.supervising_youth_heads.exists():
            for youth_head in participant.event.supervising_youth_heads.all():
                if youth_head.primary_email:
                    organizer_emails.append(youth_head.primary_email)
        
        if participant.event.supervising_CFC_coordinators.exists():
            for coordinator in participant.event.supervising_CFC_coordinators.all():
                if coordinator.primary_email:
                    organizer_emails.append(coordinator.primary_email)
        
        organizer_contact_email = organizer_emails[0] if organizer_emails else settings.DEFAULT_FROM_EMAIL
        
        # Create refund record if there are payments
        refund = None
        if has_payments:
            # Determine payment method info
            first_event_payment = event_payments.first() if event_payments.exists() else None
            payment_method_display = None
            is_automatic = False
            stripe_intent = None
            
            if first_event_payment and first_event_payment.method:
                payment_method_display = first_event_payment.method.get_method_display()
                is_automatic = first_event_payment.method.supports_automatic_refunds
                stripe_intent = first_event_payment.stripe_payment_intent
            
            print(f"💸 Initiating refund process for participant {participant.event_pax_id} - Total refund: £{total_amount}")
            # Create main ParticipantRefund (for event registration only)
            refund = ParticipantRefund.objects.create(
                participant=participant,
                event=participant.event,
                event_payment=first_event_payment,
                refund_amount=event_payment_total,  # Only event registration amount
                refund_reason=ParticipantRefund.RefundReason.ADMIN_DECISION,
                removal_reason_details=reason,
                removed_by=request.user,
                participant_email=participant.user.primary_email,
                participant_name=f"{participant.user.first_name} {participant.user.last_name}",
                refund_contact_email=organizer_contact_email,
                original_payment_method=payment_method_display,
                is_automatic_refund=is_automatic,
                status=ParticipantRefund.RefundStatus.PENDING
            )
            print(f"💰 ParticipantRefund created: {refund.refund_reference} - £{event_payment_total} (event registration)")
            
            # Create OrderRefund records for each merchandise cart
            for order_refund_data in order_refunds_to_create:
                cart = order_refund_data['cart']
                payment = order_refund_data['payment']
                amount = order_refund_data['amount']
                
                # Determine refund method for merchandise
                merch_is_automatic = False
                merch_stripe_intent = None
                merch_payment_method = None
                
                if payment.method:
                    merch_payment_method = payment.method.get_method_display()
                    merch_is_automatic = payment.method.supports_automatic_refunds
                    merch_stripe_intent = payment.stripe_payment_intent
                
                order_refund = OrderRefund.objects.create(
                    cart=cart,
                    payment=payment,
                    user=participant.user,
                    event=participant.event,
                    participant_refund=refund,  # Link to parent ParticipantRefund
                    refund_amount=amount,
                    refund_reason=OrderRefund.RefundReason.ADMIN_DECISION,
                    reason_details=f"Participant removed from event: {reason}",
                    initiated_by=request.user,
                    customer_email=participant.user.primary_email,
                    customer_name=f"{participant.user.first_name} {participant.user.last_name}",
                    refund_contact_email=organizer_contact_email,
                    original_payment_method=merch_payment_method,
                    is_automatic_refund=merch_is_automatic,
                    stripe_payment_intent=merch_stripe_intent if merch_is_automatic else None,
                    status=OrderRefund.RefundStatus.PENDING
                )
                print(f"🛍️ OrderRefund created: {order_refund.refund_reference} - £{amount} (cart: {cart.order_reference_id})")
        
        
        # Prepare payment details for email
        payment_details = {
            'has_payments': has_payments,
            'event_payment_total': event_payment_total,
            'product_payment_total': product_payment_total,
            'total_amount': total_amount,
            'merchandise_orders_count': len(order_refunds_to_create)
        }
        
        # Send removal notification email
        try:
            from apps.events.email_utils import send_participant_removal_email
            email_sent = send_participant_removal_email(
                participant=participant,
                reason=reason,
                payment_details=payment_details
            )
            if email_sent:
                print(f"📧 Participant removal email sent to {participant.user.primary_email}")
            else:
                print(f"⚠️ Participant has no email address, proceeding with removal without notification")
        except Exception as e:
            print(f"⚠️ Failed to send removal email: {e}")
            # Don't fail the removal if email fails
        
        # Store participant info before status change for response
        participant_name = participant_full_name
        event_name = participant.event.name
        
        # Change participant status to CANCELLED instead of deleting
        participant.status = EventParticipant.ParticipantStatus.CANCELLED
        participant.save()
        
        print(f"🚫 Participant {participant.event_pax_id} status changed to CANCELLED")
        
        return Response({
            'message': f'{participant_name} has been removed from {event_name}.',
            'had_payments': has_payments,
            'event_refund_amount': float(event_payment_total) if has_payments else 0,
            'merchandise_refund_amount': float(product_payment_total) if has_payments else 0,
            'total_refund_amount': float(total_amount) if has_payments else 0,
            'participant_refund_id': refund.id if refund else None,
            'participant_refund_reference': refund.refund_reference if refund else None,
            'order_refunds_count': len(order_refunds_to_create) if has_payments else 0
        }, status=status.HTTP_200_OK)
        
        # if not confirmation_name:
        #     return Response(
        #         {'error': _('Confirmation name is required.')},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )
        
        # # Validate confirmation name matches participant name
        # participant_full_name = f"{participant.user.first_name} {participant.user.last_name}"
        # if confirmation_name.lower() != participant_full_name.lower():
        #     return Response(
        #         {'error': _('Confirmation name does not match participant name.')},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )
        
        # # Calculate payment totals for refund notification
        # from decimal import Decimal
        
        # # Get all event registration payments
        # event_payments = participant.participant_event_payments.all()
        # event_payment_total = sum(
        #     payment.amount for payment in event_payments 
        #     if payment.status == EventPayment.PaymentStatus.SUCCEEDED
        # ) or Decimal('0.00')
        
        # # Get all product/merchandise payments for this event
        # product_payments = ProductPayment.objects.filter(
        #     user=participant.user, 
        #     cart__event=participant.event,
        #     status=ProductPayment.PaymentStatus.SUCCEEDED
        # )
        # product_payment_total = sum(
        #     payment.amount for payment in product_payments
        # ) or Decimal('0.00')
        
        # # Calculate total amount
        # total_amount = event_payment_total + product_payment_total
        # has_payments = total_amount > 0
        
        # # Prepare payment details for email
        # payment_details = {
        #     'has_payments': has_payments,
        #     'event_payment_total': event_payment_total,
        #     'product_payment_total': product_payment_total,
        #     'total_amount': total_amount,
        # }
        
        # # Send removal notification email
        # try:
        #     from apps.events.email_utils import send_participant_removal_email
        #     email_sent = send_participant_removal_email(
        #         participant=participant,
        #         reason=reason,
        #         payment_details=payment_details
        #     )
        #     if email_sent:
        #         print(f"📧 Participant removal email sent to {participant.user.primary_email}")
        #     else:
        #         print(f"⚠️ Participant has no email address, proceeding with removal without notification")
        # except Exception as e:
        #     print(f"⚠️ Failed to send removal email: {e}")
        #     # Don't fail the removal if email fails
        
        # # Store participant info before deletion for response
        # participant_name = participant_full_name
        # event_name = participant.event.name
        
        # # Delete the participant
        # participant.delete()
        
        # return Response({
        #     'message': f'{participant_name} has been removed from {event_name}.',
        #     'had_payments': has_payments,
        #     'total_refund_amount': float(total_amount) if has_payments else 0
        # }, status=status.HTTP_200_OK)

class EventTalkViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event talks.
    '''
    queryset = EventTalk.objects.all()
    serializer_class = EventTalkSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'speaker', 'talk_type', 'is_published']
    ordering_fields = ['start_time', 'end_time']
    ordering = ['start_time']

class EventWorkshopViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event workshops.
    '''
    queryset = EventWorkshop.objects.all()
    serializer_class = EventWorkshopSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'primary_facilitator', 'level', 'is_published', 'is_full']
    ordering_fields = ['start_time', 'end_time', 'max_participants']
    ordering = ['start_time']
    
    @action(detail=True, methods=['post'])
    def add_facilitator(self, request, pk=None):
        workshop = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            user = get_user_model().objects.get(id=user_id)
            workshop.facilitators.add(user)
            workshop.save()
            serializer = self.get_serializer(workshop)
            return Response(serializer.data)
        except get_user_model().DoesNotExist:
            return Response(
                {'error': _('User not found')},
                status=status.HTTP_404_NOT_FOUND
            )

class PublicEventResourceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing public event resources (memos, files, links).
    """
    queryset = EventResource.objects.all()
    serializer_class = PublicEventResourceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # anyone can GET, only logged-in can modify

class EventDayAttendanceViewSet(viewsets.ModelViewSet):
    '''
    API endpoint for managing event day attendance.
    '''
    queryset = EventDayAttendance.objects.select_related("event", "user")
    serializer_class = EventDayAttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["event", "user"]
    search_fields = ["user__first_name", "user__last_name", "event__name"]
    ordering_fields = ["check_in_time", "check_out_time"]
    ordering = ["-check_in_time"]
    permission_classes = [permissions.IsAuthenticated]
    