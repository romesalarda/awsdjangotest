"""
ViewSet for managing participant refunds.
Provides comprehensive refund tracking, filtering, and processing capabilities.
"""
from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.events.models import ParticipantRefund, EventParticipant
from apps.events.api.serializers import (
    ParticipantRefundListSerializer,
    ParticipantRefundDetailSerializer,
    ProcessRefundSerializer,
    CreateRefundSerializer
)
from apps.events.email_utils import send_refund_processed_email
import threading


class ParticipantRefundViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing participant refunds.
    
    Provides comprehensive refund tracking with advanced filtering:
    - Filter by event, status, date ranges
    - Search by participant name, email, refund reference
    - Sort by amount, date, status
    - Batch operations for processing multiple refunds
    
    list: Get all refunds with lightweight data
    retrieve: Get detailed refund information
    create: Create a new refund record (typically done automatically)
    update: Update refund details
    partial_update: Partially update refund
    destroy: Delete refund record (admin only)
    
    Custom actions:
    - process_refund: Mark refund as processed and send confirmation email
    - pending_refunds: Get all pending refunds
    - refund_statistics: Get refund statistics for events
    """
    
    queryset = ParticipantRefund.objects.select_related(
        'participant',
        'participant__user',
        'event',
        'removed_by',
        'processed_by'
    ).all()
    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Filtering options
    filterset_fields = {
        'status': ['exact', 'in'],
        'event': ['exact'],
        # 'participant': removed - we handle participant filtering manually in get_queryset() by event_pax_id
        'created_at': ['gte', 'lte', 'exact'],
        'processed_at': ['gte', 'lte', 'isnull'],
        'total_refund_amount': ['gte', 'lte', 'exact'],
    }
    
    # Search functionality
    search_fields = [
        'refund_reference',
        'participant__user__first_name',
        'participant__user__last_name',
        'participant__user__primary_email',
        'participant_email',
        'event__name',
        'event__event_code',
        'removal_reason'
    ]
    
    # Sorting options
    ordering_fields = [
        'created_at',
        'processed_at',
        'total_refund_amount',
        'status',
        'event__start_date'
    ]
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return ParticipantRefundListSerializer
        elif self.action in ['process_refund']:
            return ProcessRefundSerializer
        elif self.action == 'create':
            return CreateRefundSerializer
        return ParticipantRefundDetailSerializer
    
    def get_queryset(self):
        """Filter queryset based on permissions and query params"""
        queryset = super().get_queryset()
        
        # Filter by event if provided
        event_id = self.request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event__id=event_id)
        
        # Filter by participant event_pax_id if provided (e.g., ?participant=YYC2025LUMOS-83E5579)
        participant_event_pax_id = self.request.query_params.get('participant')
        if participant_event_pax_id:
            queryset = queryset.filter(participant__event_pax_id=participant_event_pax_id)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status_filter')
        if status_filter:
            if status_filter == 'pending':
                queryset = queryset.filter(
                    status__in=[
                        ParticipantRefund.RefundStatus.PENDING,
                        ParticipantRefund.RefundStatus.IN_PROGRESS
                    ]
                )
            elif status_filter == 'processed':
                queryset = queryset.filter(status=ParticipantRefund.RefundStatus.PROCESSED)
        
        # Filter by participant with payments
        has_payments = self.request.query_params.get('has_payments')
        if has_payments == 'true':
            queryset = queryset.filter(total_refund_amount__gt=0)
        elif has_payments == 'false':
            queryset = queryset.filter(total_refund_amount=0)
        
        return queryset
    
    @action(detail=True, methods=['post'], url_name='process-refund', url_path='process')
    def process_refund(self, request, pk=None):
        """
        Mark a refund as processed and send confirmation email to participant.
        
        Request body:
        {
            "processing_notes": "Refund sent via bank transfer",
            "refund_method": "Bank Transfer"
        }
        """
        refund = self.get_object()
        
        serializer = ProcessRefundSerializer(
            data=request.data,
            context={'refund': refund, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        
        # Send confirmation email to participant in background
        def send_email():
            try:
                send_refund_processed_email(refund)
                print(f"📧 Refund processed email sent for {refund.refund_reference}")
            except Exception as e:
                print(f"⚠️ Failed to send refund processed email: {e}")
        
        email_thread = threading.Thread(target=send_email)
        email_thread.start()
        
        # Return detailed refund data
        response_serializer = ParticipantRefundDetailSerializer(refund)
        return Response({
            'message': _('Refund processed successfully. Confirmation email sent to participant.'),
            'refund': response_serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_name='pending-refunds', url_path='pending')
    def pending_refunds(self, request):
        """
        Get all pending refunds (not yet processed).
        Useful for admin dashboard to see outstanding refunds.
        """
        queryset = self.get_queryset().filter(
            status__in=[
                ParticipantRefund.RefundStatus.PENDING,
                ParticipantRefund.RefundStatus.IN_PROGRESS
            ]
        )
        
        # Apply standard filtering
        queryset = self.filter_queryset(queryset)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_name='statistics', url_path='statistics')
    def refund_statistics(self, request):
        """
        Get refund statistics across all events or for a specific event.
        
        Query params:
        - event_id: Filter statistics for specific event
        
        Returns aggregated data about refunds.
        """
        queryset = self.get_queryset()
        
        # Calculate statistics
        stats = queryset.aggregate(
            total_refunds=Count('id'),
            total_amount=Sum('total_refund_amount'),
            pending_count=Count('id', filter=Q(
                status__in=[
                    ParticipantRefund.RefundStatus.PENDING,
                    ParticipantRefund.RefundStatus.IN_PROGRESS
                ]
            )),
            pending_amount=Sum('total_refund_amount', filter=Q(
                status__in=[
                    ParticipantRefund.RefundStatus.PENDING,
                    ParticipantRefund.RefundStatus.IN_PROGRESS
                ]
            )),
            processed_count=Count('id', filter=Q(status=ParticipantRefund.RefundStatus.PROCESSED)),
            processed_amount=Sum('total_refund_amount', filter=Q(status=ParticipantRefund.RefundStatus.PROCESSED))
        )
        
        # Get breakdown by event if no specific event filter
        event_id = request.query_params.get('event_id')
        if not event_id:
            event_breakdown = queryset.values(
                'event__id',
                'event__name',
                'event__event_code'
            ).annotate(
                refund_count=Count('id'),
                total_amount=Sum('total_refund_amount'),
                pending_count=Count('id', filter=Q(
                    status__in=[
                        ParticipantRefund.RefundStatus.PENDING,
                        ParticipantRefund.RefundStatus.IN_PROGRESS
                    ]
                ))
            ).order_by('-total_amount')[:10]  # Top 10 events
            
            stats['top_events'] = list(event_breakdown)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], url_name='by-participant', url_path='by-participant/(?P<event_pax_id>[^/.]+)')
    def by_participant(self, request, event_pax_id=None):
        """
        Get refund by participant's event_pax_id.
        
        URL: /api/events/payments/refunds/by-participant/{event_pax_id}/
        Example: /api/events/payments/refunds/by-participant/YYC2025LUMOS-83E5579/
        """
        try:
            refund = ParticipantRefund.objects.select_related(
                'participant',
                'participant__user',
                'event',
                'removed_by',
                'processed_by'
            ).get(participant__event_pax_id=event_pax_id)
            
            serializer = ParticipantRefundDetailSerializer(refund)
            return Response(serializer.data)
        except ParticipantRefund.DoesNotExist:
            return Response(
                {'error': _('No refund found for participant with ID: %(id)s') % {'id': event_pax_id}},
                status=status.HTTP_404_NOT_FOUND
            )
        except ParticipantRefund.MultipleObjectsReturned:
            # If multiple refunds exist for same participant, return the most recent
            refund = ParticipantRefund.objects.select_related(
                'participant',
                'participant__user',
                'event',
                'removed_by',
                'processed_by'
            ).filter(participant__event_pax_id=event_pax_id).order_by('-created_at').first()
            
            serializer = ParticipantRefundDetailSerializer(refund)
            return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_name='update-status', url_path='update-status')
    def update_status(self, request, pk=None):
        """
        Update refund status (e.g., from PENDING to IN_PROGRESS).
        
        Request body:
        {
            "status": "IN_PROGRESS",
            "processing_notes": "Awaiting bank confirmation"
        }
        """
        refund = self.get_object()
        
        new_status = request.data.get('status')
        if not new_status:
            return Response(
                {'error': _('Status is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate status
        valid_statuses = [choice[0] for choice in ParticipantRefund.RefundStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': _('Invalid status')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status
        refund.status = new_status
        
        # Update processing notes if provided
        if request.data.get('processing_notes'):
            refund.processing_notes = request.data['processing_notes']
        
        refund.save()
        
        serializer = ParticipantRefundDetailSerializer(refund)
        return Response({
            'message': _('Refund status updated successfully'),
            'refund': serializer.data
        })
