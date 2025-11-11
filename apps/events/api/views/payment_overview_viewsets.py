"""
Payment Overview ViewSets
Provides comprehensive payment analytics, revenue tracking, donations, and timeline data.
"""

from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count, Avg, F, Case, When, DecimalField
from django.db.models.functions import TruncDate, Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.events.models import (
    Event, EventPayment, DonationPayment, ParticipantRefund,
    EventParticipant
)
from apps.shop.models import ProductPayment
from apps.events.api.serializers.payment_overview_serializers import (
    PaymentOverviewSerializer,
    PaymentTimelineSerializer,
    RevenueBreakdownSerializer,
    PaymentMethodBreakdownSerializer,
    LocationPaymentBreakdownSerializer,
    DonationListSerializer,
    DonationDetailSerializer,
    DonationSummarySerializer
)
from core.event_permissions import has_event_permission


class PaymentOverviewViewSet(viewsets.ViewSet):
    """
    ViewSet for comprehensive payment analytics and reporting.
    Provides endpoints for timeline data, revenue calculations, and location breakdowns.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/overview')
    def event_overview(self, request, event_id=None):
        """
        Get comprehensive payment overview for an event.
        Includes timeline, revenue breakdown, payment methods, and location analysis.
        
        Query params:
        - granularity: 'daily', 'weekly', 'monthly' (default: daily)
        - include_pending: true/false (default: true)
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response(
                {'error': 'Event not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view payments for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        granularity = request.query_params.get('granularity', 'daily')
        include_pending = request.query_params.get('include_pending', 'true').lower() == 'true'
        
        # Get revenue breakdown
        revenue_breakdown = self._get_revenue_breakdown(event, include_pending)
        
        # Calculate additional metrics
        total_payments = (
            revenue_breakdown['event_registration_count'] + 
            revenue_breakdown['merchandise_count']
        )
        verified_payments = EventPayment.objects.filter(
            event=event,
            verified=True,
            status=EventPayment.PaymentStatus.SUCCEEDED
        ).count()
        pending_payments = EventPayment.objects.filter(
            event=event,
            verified=False,
            status__in=[EventPayment.PaymentStatus.SUCCEEDED, EventPayment.PaymentStatus.PENDING]
        ).count()
        
        # Calculate average payment
        average_payment = Decimal('0.00')
        if total_payments > 0:
            average_payment = revenue_breakdown['gross_revenue'] / total_payments
        
        # Build overview data (flattened structure for frontend)
        overview_data = {
            # Event metadata
            'event_id': str(event.id),
            'event_name': event.name,
            'event_code': event.event_code,
            
            # Revenue summary (flattened from revenue_breakdown)
            'gross_revenue': revenue_breakdown['gross_revenue'],
            'net_revenue': revenue_breakdown['net_revenue'],
            'verified_revenue': revenue_breakdown['total_verified_revenue'],
            'pending_revenue': revenue_breakdown['total_pending_revenue'],
            
            # Payment counts
            'total_payments': total_payments,
            'verified_payments': verified_payments,
            'pending_payments': pending_payments,
            
            # Refunds
            'total_refunds': revenue_breakdown['total_refunds'],
            'refund_count': revenue_breakdown['refund_count'],
            
            # Donations
            'total_donations': revenue_breakdown['donation_revenue'],
            'donation_count': revenue_breakdown['donation_count'],
            
            # Averages
            'average_payment': average_payment,
            
            # Participant stats
            'total_participants': EventParticipant.objects.filter(event=event).count(),
            'participants_paid': self._get_participants_paid_count(event, include_pending),
            'participants_pending': EventPayment.objects.filter(
                event=event,
                status=EventPayment.PaymentStatus.PENDING
            ).values('user').distinct().count(),
            'payment_completion_rate': 0.0,
            
            # Date range
            'earliest_payment': None,
            'latest_payment': None,
            'generated_at': timezone.now()
        }
        
        # Calculate completion rate
        if overview_data['total_participants'] > 0:
            overview_data['payment_completion_rate'] = round(
                (overview_data['participants_paid'] / overview_data['total_participants']) * 100,
                2
            )
        
        # Get date range
        payment_dates = EventPayment.objects.filter(event=event).aggregate(
            earliest=Coalesce(Min('created_at'), None),
            latest=Coalesce(Max('created_at'), None)
        )
        overview_data['earliest_payment'] = payment_dates['earliest']
        overview_data['latest_payment'] = payment_dates['latest']
        
        return Response(overview_data)
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/timeline')
    def event_timeline(self, request, event_id=None):
        """
        Get payment timeline data for graphs.
        Returns daily/weekly/monthly payment activity.
        
        Query params:
        - granularity: 'daily', 'weekly', 'monthly' (default: daily)
        - include_pending: true/false (default: true)
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view payments for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        granularity = request.query_params.get('granularity', 'daily')
        include_pending = request.query_params.get('include_pending', 'true').lower() == 'true'
        
        timeline_data = self._get_timeline_data(event, granularity, include_pending)
        serializer = PaymentTimelineSerializer(timeline_data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/revenue')
    def event_revenue(self, request, event_id=None):
        """
        Get detailed revenue breakdown for an event.
        
        Query params:
        - include_pending: true/false (default: true)
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view payments for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        include_pending = request.query_params.get('include_pending', 'true').lower() == 'true'
        revenue_data = self._get_revenue_breakdown(event, include_pending)
        serializer = RevenueBreakdownSerializer(revenue_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/by-location')
    def event_by_location(self, request, event_id=None):
        """
        Get payment breakdown by location (area/chapter/cluster).
        
        Query params:
        - group_by: 'area', 'chapter', 'cluster' (default: area)
        - include_pending: true/false (default: true)
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view payments for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        group_by = request.query_params.get('group_by', 'area')
        include_pending = request.query_params.get('include_pending', 'true').lower() == 'true'
        
        location_data = self._get_location_breakdown(event, include_pending, group_by)
        serializer = LocationPaymentBreakdownSerializer(location_data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/payment-methods')
    def event_payment_methods(self, request, event_id=None):
        """
        Get payment method breakdown for an event.
        
        Query params:
        - include_pending: true/false (default: true)
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view payments for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        include_pending = request.query_params.get('include_pending', 'true').lower() == 'true'
        payment_method_data = self._get_payment_method_breakdown(event, include_pending)
        serializer = PaymentMethodBreakdownSerializer(payment_method_data, many=True)
        return Response(serializer.data)
    
    # Helper methods for data aggregation
    
    def _get_revenue_breakdown(self, event, include_pending=True):
        """Calculate comprehensive revenue breakdown"""
        # Event registration payments
        event_payment_filter = Q(event=event)
        if include_pending:
            event_payment_filter &= Q(status__in=[
                EventPayment.PaymentStatus.SUCCEEDED,
                EventPayment.PaymentStatus.PENDING
            ])
        else:
            event_payment_filter &= Q(status=EventPayment.PaymentStatus.SUCCEEDED)
        
        event_payments = EventPayment.objects.filter(event_payment_filter).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00')),
            count=Count('id'),
            verified_amount=Coalesce(Sum('amount', filter=Q(verified=True)), Decimal('0.00')),
            pending_amount=Coalesce(Sum('amount', filter=Q(verified=False)), Decimal('0.00'))
        )
        
        # Merchandise payments
        product_payment_filter = Q(cart__event=event)
        if include_pending:
            product_payment_filter &= Q(status__in=[
                ProductPayment.PaymentStatus.SUCCEEDED,
                ProductPayment.PaymentStatus.PENDING
            ])
        else:
            product_payment_filter &= Q(status=ProductPayment.PaymentStatus.SUCCEEDED)
        
        product_payments = ProductPayment.objects.filter(product_payment_filter).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00')),
            count=Count('id'),
            verified_amount=Coalesce(Sum('amount', filter=Q(approved=True)), Decimal('0.00')),
            pending_amount=Coalesce(Sum('amount', filter=Q(approved=False)), Decimal('0.00'))
        )
        
        # Donations
        donation_filter = Q(event=event)
        if include_pending:
            donation_filter &= Q(status__in=[
                DonationPayment.PaymentStatus.SUCCEEDED,
                DonationPayment.PaymentStatus.PENDING
            ])
        else:
            donation_filter &= Q(status=DonationPayment.PaymentStatus.SUCCEEDED)
        
        donations = DonationPayment.objects.filter(donation_filter).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00')),
            count=Count('id'),
            verified_amount=Coalesce(Sum('amount', filter=Q(verified=True)), Decimal('0.00')),
            pending_amount=Coalesce(Sum('amount', filter=Q(verified=False)), Decimal('0.00'))
        )
        
        # Refunds
        refunds = ParticipantRefund.objects.filter(event=event).aggregate(
            total=Coalesce(Sum('total_refund_amount'), Decimal('0.00')),
            count=Count('id'),
            processed_amount=Coalesce(Sum(
                'total_refund_amount',
                filter=Q(status=ParticipantRefund.RefundStatus.PROCESSED)
            ), Decimal('0.00')),
            pending_amount=Coalesce(Sum(
                'total_refund_amount',
                filter=Q(status__in=[
                    ParticipantRefund.RefundStatus.PENDING,
                    ParticipantRefund.RefundStatus.IN_PROGRESS
                ])
            ), Decimal('0.00'))
        )
        
        # Calculate totals
        gross_revenue = (
            event_payments['total'] +
            product_payments['total'] +
            donations['total']
        )
        
        net_revenue = gross_revenue - refunds['processed_amount']
        
        total_verified = (
            event_payments['verified_amount'] +
            product_payments['verified_amount'] +
            donations['verified_amount']
        ) - refunds['processed_amount']
        
        total_pending = (
            event_payments['pending_amount'] +
            product_payments['pending_amount'] +
            donations['pending_amount']
        )
        
        return {
            'event_registration_revenue': event_payments['total'],
            'event_registration_count': event_payments['count'],
            'event_registration_verified': event_payments['verified_amount'],
            'event_registration_pending': event_payments['pending_amount'],
            'merchandise_revenue': product_payments['total'],
            'merchandise_count': product_payments['count'],
            'merchandise_verified': product_payments['verified_amount'],
            'merchandise_pending': product_payments['pending_amount'],
            'donation_revenue': donations['total'],
            'donation_count': donations['count'],
            'donation_verified': donations['verified_amount'],
            'donation_pending': donations['pending_amount'],
            'total_refunds': refunds['total'],
            'refund_count': refunds['count'],
            'processed_refunds': refunds['processed_amount'],
            'pending_refunds': refunds['pending_amount'],
            'gross_revenue': gross_revenue,
            'net_revenue': net_revenue,
            'total_verified_revenue': total_verified,
            'total_pending_revenue': total_pending,
            'currency': 'gbp'
        }
    
    def _get_timeline_data(self, event, granularity='daily', include_pending=True):
        """Generate timeline data for graphing"""
        # Determine date range
        start_date = event.registration_open_date or event.created_at or timezone.now() - timedelta(days=30)
        end_date = timezone.now()
        
        # Truncate function based on granularity
        if granularity == 'monthly':
            trunc_func = TruncMonth
            delta = timedelta(days=30)
        elif granularity == 'weekly':
            trunc_func = TruncWeek
            delta = timedelta(weeks=1)
        else:  # daily
            trunc_func = TruncDate
            delta = timedelta(days=1)
        
        # Get event payments by date
        event_payment_filter = Q(event=event)
        if include_pending:
            event_payment_filter &= Q(status__in=[
                EventPayment.PaymentStatus.SUCCEEDED,
                EventPayment.PaymentStatus.PENDING
            ])
        else:
            event_payment_filter &= Q(status=EventPayment.PaymentStatus.SUCCEEDED)
        
        event_payments_timeline = EventPayment.objects.filter(event_payment_filter).annotate(
            date=trunc_func('created_at')
        ).values('date').annotate(
            count=Count('id'),
            amount=Coalesce(Sum('amount'), Decimal('0.00'))
        ).order_by('date')
        
        # Get product payments by date
        product_payment_filter = Q(cart__event=event)
        if include_pending:
            product_payment_filter &= Q(status__in=[
                ProductPayment.PaymentStatus.SUCCEEDED,
                ProductPayment.PaymentStatus.PENDING
            ])
        else:
            product_payment_filter &= Q(status=ProductPayment.PaymentStatus.SUCCEEDED)
        
        product_payments_timeline = ProductPayment.objects.filter(product_payment_filter).annotate(
            date=trunc_func('created_at')
        ).values('date').annotate(
            count=Count('id'),
            amount=Coalesce(Sum('amount'), Decimal('0.00'))
        ).order_by('date')
        
        # Get donations by date
        donation_filter = Q(event=event)
        if include_pending:
            donation_filter &= Q(status__in=[
                DonationPayment.PaymentStatus.SUCCEEDED,
                DonationPayment.PaymentStatus.PENDING
            ])
        else:
            donation_filter &= Q(status=DonationPayment.PaymentStatus.SUCCEEDED)
        
        donations_timeline = DonationPayment.objects.filter(donation_filter).annotate(
            date=trunc_func('created_at')
        ).values('date').annotate(
            count=Count('id'),
            amount=Coalesce(Sum('amount'), Decimal('0.00'))
        ).order_by('date')
        
        # Get refunds by date
        refunds_timeline = ParticipantRefund.objects.filter(
            event=event,
            status=ParticipantRefund.RefundStatus.PROCESSED
        ).annotate(
            date=trunc_func('processed_at')
        ).values('date').annotate(
            count=Count('id'),
            amount=Coalesce(Sum('total_refund_amount'), Decimal('0.00'))
        ).order_by('date')
        
        # Combine all data by date
        timeline_dict = {}
        
        for payment in event_payments_timeline:
            date = payment['date'].date() if hasattr(payment['date'], 'date') else payment['date']
            if date not in timeline_dict:
                timeline_dict[date] = self._init_timeline_entry(date)
            timeline_dict[date]['event_registrations'] = payment['count']
            timeline_dict[date]['event_registration_amount'] = payment['amount']
        
        for payment in product_payments_timeline:
            date = payment['date'].date() if hasattr(payment['date'], 'date') else payment['date']
            if date not in timeline_dict:
                timeline_dict[date] = self._init_timeline_entry(date)
            timeline_dict[date]['merchandise_orders'] = payment['count']
            timeline_dict[date]['merchandise_amount'] = payment['amount']
        
        for donation in donations_timeline:
            date = donation['date'].date() if hasattr(donation['date'], 'date') else donation['date']
            if date not in timeline_dict:
                timeline_dict[date] = self._init_timeline_entry(date)
            timeline_dict[date]['donations'] = donation['count']
            timeline_dict[date]['donation_amount'] = donation['amount']
        
        for refund in refunds_timeline:
            date = refund['date'].date() if hasattr(refund['date'], 'date') else refund['date']
            if date not in timeline_dict:
                timeline_dict[date] = self._init_timeline_entry(date)
            timeline_dict[date]['refunds'] = refund['count']
            timeline_dict[date]['refund_amount'] = refund['amount']
        
        # Calculate net and cumulative amounts
        cumulative = Decimal('0.00')
        timeline_list = []
        for date in sorted(timeline_dict.keys()):
            entry = timeline_dict[date]
            entry['net_amount'] = (
                entry['event_registration_amount'] +
                entry['merchandise_amount'] +
                entry['donation_amount'] -
                entry['refund_amount']
            )
            cumulative += entry['net_amount']
            entry['cumulative_amount'] = cumulative
            timeline_list.append(entry)
        
        return timeline_list
    
    def _init_timeline_entry(self, date):
        """Initialize empty timeline entry"""
        return {
            'date': date,
            'event_registrations': 0,
            'event_registration_amount': Decimal('0.00'),
            'merchandise_orders': 0,
            'merchandise_amount': Decimal('0.00'),
            'donations': 0,
            'donation_amount': Decimal('0.00'),
            'refunds': 0,
            'refund_amount': Decimal('0.00'),
            'net_amount': Decimal('0.00'),
            'cumulative_amount': Decimal('0.00')
        }
    
    def _get_payment_method_breakdown(self, event, include_pending=True):
        """Get payment method distribution"""
        # Combine event and product payments
        payment_methods = {}
        
        # Event payments
        event_filter = Q(event=event, method__isnull=False)
        if include_pending:
            event_filter &= Q(status__in=[
                EventPayment.PaymentStatus.SUCCEEDED,
                EventPayment.PaymentStatus.PENDING
            ])
        else:
            event_filter &= Q(status=EventPayment.PaymentStatus.SUCCEEDED)
        
        event_payments = EventPayment.objects.filter(event_filter).values(
            'method__method'
        ).annotate(
            count=Count('id'),
            total_amount=Coalesce(Sum('amount'), Decimal('0.00'))
        )
        
        for payment in event_payments:
            method = payment['method__method']
            if method not in payment_methods:
                payment_methods[method] = {'count': 0, 'total_amount': Decimal('0.00')}
            payment_methods[method]['count'] += payment['count']
            payment_methods[method]['total_amount'] += payment['total_amount']
        
        # Product payments
        product_filter = Q(cart__event=event, method__isnull=False)
        if include_pending:
            product_filter &= Q(status__in=[
                ProductPayment.PaymentStatus.SUCCEEDED,
                ProductPayment.PaymentStatus.PENDING
            ])
        else:
            product_filter &= Q(status=ProductPayment.PaymentStatus.SUCCEEDED)
        
        product_payments = ProductPayment.objects.filter(product_filter).values(
            'method__method'
        ).annotate(
            count=Count('id'),
            total_amount=Coalesce(Sum('amount'), Decimal('0.00'))
        )
        
        for payment in product_payments:
            method = payment['method__method']
            if method not in payment_methods:
                payment_methods[method] = {'count': 0, 'total_amount': Decimal('0.00')}
            payment_methods[method]['count'] += payment['count']
            payment_methods[method]['total_amount'] += payment['total_amount']
        
        # Calculate total and percentages
        total_amount = sum(pm['total_amount'] for pm in payment_methods.values())
        
        result = []
        for method, data in payment_methods.items():
            percentage = (float(data['total_amount']) / float(total_amount) * 100) if total_amount > 0 else 0
            average = data['total_amount'] / data['count'] if data['count'] > 0 else Decimal('0.00')
            
            # Get display name
            from apps.events.models import EventPaymentMethod
            method_display = dict(EventPaymentMethod.MethodType.choices).get(method, method)
            
            result.append({
                'method': method,
                'method_display': method_display,
                'count': data['count'],
                'total_amount': data['total_amount'],
                'percentage': round(percentage, 2),
                'average_transaction': average
            })
        
        return sorted(result, key=lambda x: x['total_amount'], reverse=True)
    
    def _get_location_breakdown(self, event, include_pending=True, group_by='area'):
        """Get payment breakdown by location"""
        # Get participants with payments
        participants = EventParticipant.objects.filter(event=event).select_related(
            'user',
            'user__area_from',
            'user__area_from__unit',
            'user__area_from__unit__chapter',
            'user__area_from__unit__chapter__cluster'
        )
        
        location_data = {}
        
        for participant in participants:
            # Skip if user or area_from is None
            if not participant.user or not participant.user.area_from:
                continue
                
            area_from = participant.user.area_from
            
            # Determine location based on group_by
            if group_by == 'cluster' and area_from.unit and area_from.unit.chapter:
                location_id = str(area_from.unit.chapter.cluster.cluster_id)
                location_name = area_from.unit.chapter.cluster.cluster_id
                location_type = 'cluster'
            elif group_by == 'chapter' and area_from.unit:
                location_id = str(area_from.unit.chapter.id)
                location_name = area_from.unit.chapter.chapter_name
                location_type = 'chapter'
            else:  # area (default)
                location_id = str(area_from.id)
                location_name = area_from.area_name
                location_type = 'area'
            
            if location_id not in location_data:
                location_data[location_id] = {
                    'location_id': location_id,
                    'location_name': location_name,
                    'location_type': location_type,
                    'total_participants': 0,
                    'total_payments': 0,
                    'total_amount': Decimal('0.00'),
                    'verified_payments': 0,
                    'verified_amount': Decimal('0.00'),
                    'pending_payments': 0,
                    'pending_amount': Decimal('0.00')
                }
            
            location_data[location_id]['total_participants'] += 1
            
            # Get payments for this participant
            event_filter = Q(user=participant, event=event)
            if include_pending:
                event_filter &= Q(status__in=[
                    EventPayment.PaymentStatus.SUCCEEDED,
                    EventPayment.PaymentStatus.PENDING
                ])
            else:
                event_filter &= Q(status=EventPayment.PaymentStatus.SUCCEEDED)
            
            payments = EventPayment.objects.filter(event_filter).aggregate(
                count=Count('id'),
                total=Coalesce(Sum('amount'), Decimal('0.00')),
                verified_count=Count('id', filter=Q(verified=True)),
                verified_amount=Coalesce(Sum('amount', filter=Q(verified=True)), Decimal('0.00')),
                pending_count=Count('id', filter=Q(verified=False)),
                pending_amount=Coalesce(Sum('amount', filter=Q(verified=False)), Decimal('0.00'))
            )
            
            location_data[location_id]['total_payments'] += payments['count']
            location_data[location_id]['total_amount'] += payments['total']
            location_data[location_id]['verified_payments'] += payments['verified_count']
            location_data[location_id]['verified_amount'] += payments['verified_amount']
            location_data[location_id]['pending_payments'] += payments['pending_count']
            location_data[location_id]['pending_amount'] += payments['pending_amount']
        
        # Calculate averages
        result = []
        for location in location_data.values():
            if location['total_payments'] > 0:
                location['average_payment'] = location['total_amount'] / location['total_payments']
            else:
                location['average_payment'] = Decimal('0.00')
            result.append(location)
        
        return sorted(result, key=lambda x: x['total_amount'], reverse=True)
    
    def _get_participants_paid_count(self, event, include_pending=True):
        """Get count of unique participants who have paid"""
        payment_filter = Q(event=event)
        if include_pending:
            payment_filter &= Q(status__in=[
                EventPayment.PaymentStatus.SUCCEEDED,
                EventPayment.PaymentStatus.PENDING
            ])
        else:
            payment_filter &= Q(status=EventPayment.PaymentStatus.SUCCEEDED)
        
        return EventPayment.objects.filter(payment_filter).values('user').distinct().count()


# Import after class definition to avoid circular imports
from django.db.models.functions import TruncMonth, TruncWeek
from django.db.models import Min, Max

class DonationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing event donations.
    Provides list and detail views with filtering and statistics.
    """
    queryset = DonationPayment.objects.select_related(
        'user',
        'user__user',
        'user__user__area_from',
        'event',
        'method'
    ).all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'event': ['exact'],
        'status': ['exact', 'in'],
        'verified': ['exact'],
        'pay_to_event': ['exact'],
        'amount': ['gte', 'lte'],
        'created_at': ['gte', 'lte'],
        'paid_at': ['gte', 'lte', 'isnull']
    }
    
    search_fields = [
        'event_payment_tracking_number',
        'bank_reference',
        'user__user__area_from__first_name',
        'user__user__area_from__last_name',
        'user__user__email'
    ]
    
    ordering_fields = ['amount', 'created_at', 'paid_at', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter queryset based on permissions"""
        queryset = super().get_queryset()
        
        # Filter by event if provided
        event_id = self.request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event__id=event_id)
            
            # Check permission for this event
            try:
                event = Event.objects.get(id=event_id)
                if not has_event_permission(self.request.user, event, 'can_view_payments'):
                    return DonationPayment.objects.none()
            except Event.DoesNotExist:
                return DonationPayment.objects.none()
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """List donations with serialized data"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            data = self._serialize_donations(page)
            return self.get_paginated_response(data)
        
        data = self._serialize_donations(queryset)
        return Response(data)
    
    def retrieve(self, request, *args, **kwargs):
        """Get detailed donation information"""
        instance = self.get_object()
        data = self._serialize_donation_detail(instance)
        return Response(data)
    
    @action(detail=False, methods=['get'], url_path='event/(?P<event_id>[^/.]+)/summary')
    def event_summary(self, request, event_id=None):
        """
        Get donation summary statistics for an event.
        """
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not has_event_permission(request.user, event, 'can_view_payments'):
            return Response(
                {'error': 'You do not have permission to view donations for this event'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        donations = DonationPayment.objects.filter(event=event)
        
        summary = donations.aggregate(
            total_donations=Count('id'),
            total_amount=Coalesce(Sum('amount'), Decimal('0.00')),
            verified_donations=Count('id', filter=Q(verified=True)),
            verified_amount=Coalesce(Sum('amount', filter=Q(verified=True)), Decimal('0.00')),
            pending_donations=Count('id', filter=Q(verified=False)),
            pending_amount=Coalesce(Sum('amount', filter=Q(verified=False)), Decimal('0.00')),
            average_donation=Coalesce(Avg('amount'), Decimal('0.00')),
            largest_donation=Coalesce(Max('amount'), Decimal('0.00')),
            donations_for_event=Count('id', filter=Q(pay_to_event=True)),
            donations_for_event_amount=Coalesce(Sum('amount', filter=Q(pay_to_event=True)), Decimal('0.00'))
        )
        
        summary['currency'] = 'gbp'
        serializer = DonationSummarySerializer(summary)
        return Response(serializer.data)
    
    def _serialize_donations(self, queryset):
        """Serialize donations for list view"""
        data = []
        for donation in queryset:
            data.append({
                'id': str(donation.id),
                'donor_name': self._get_donor_name(donation),
                'donor_email': self._get_donor_email(donation),
                'amount': float(donation.amount),
                'currency': donation.currency,
                'payment_method': donation.method.get_method_display() if donation.method else 'Unknown',
                'status': donation.status,
                'status_display': donation.get_status_display(),
                'verified': donation.verified,
                'pay_to_event': donation.pay_to_event,
                'tracking_number': donation.event_payment_tracking_number,
                'created_at': donation.created_at,
                'paid_at': donation.paid_at,
                'participant_area': self._get_participant_area(donation),
                'participant_chapter': self._get_participant_chapter(donation)
            })
        return data
    
    def _serialize_donation_detail(self, donation):
        """Serialize donation for detail view"""
        return {
            'id': str(donation.id),
            'donor_name': self._get_donor_name(donation),
            'donor_email': self._get_donor_email(donation),
            'donor_phone': self._get_donor_phone(donation),
            'amount': float(donation.amount),
            'currency': donation.currency,
            'payment_method': donation.method.method if donation.method else None,
            'payment_method_display': donation.method.get_method_display() if donation.method else 'Unknown',
            'status': donation.status,
            'status_display': donation.get_status_display(),
            'verified': donation.verified,
            'pay_to_event': donation.pay_to_event,
            'tracking_number': donation.event_payment_tracking_number,
            'bank_reference': donation.bank_reference,
            'stripe_payment_intent': donation.stripe_payment_intent,
            'created_at': donation.created_at,
            'paid_at': donation.paid_at,
            'updated_at': donation.updated_at,
            'participant_details': self._get_participant_details(donation)
        }
    
    def _get_donor_name(self, donation:DonationPayment):
        """Get donor full name"""
        if donation.user and donation.user.user and donation.user.user.area_from:
            profile = donation.user.user
            return f"{profile.first_name} {profile.last_name}"
        elif donation.user and donation.user.user:
            return donation.user.user.get_full_name()
        return "Anonymous"
    
    def _get_donor_email(self, donation):
        """Get donor email"""
        if donation.user and donation.user.user:
            if donation.user.user:
                return donation.user.user.primary_email
            return donation.user.user.primary_email
        return None
    
    def _get_donor_phone(self, donation):
        """Get donor phone"""
        if donation.user and donation.user.user:
            return donation.user.user.phone_number
        return None
    
    def _get_participant_area(self, donation):
        """Get participant area name"""
        if donation.user and donation.user.user.area_from:
            return donation.user.user.area_from.area_name
        return None
    
    def _get_participant_chapter(self, donation):
        """Get participant chapter name"""
        if donation.user and donation.user.user.area_from and donation.user.user.area_from.unit:
            return donation.user.user.area_from.unit.chapter.chapter_name
        return None
    
    def _get_participant_details(self, donation):
        """Get detailed participant information"""
        if not donation.user:
            return None
        
        details = {
            'event_pax_id': donation.user.event_pax_id,
            'status': donation.user.user.get_status_display()
        }
        
        if donation.user.area:
            details['area'] = {
                'id': str(donation.user.user.area_from.id),
                'name': donation.user.user.area_from.area_name,
                'code': donation.user.user.area_from.area_code
            }
            
            if donation.user.area.unit:
                details['chapter'] = {
                    'id': str(donation.user.user.area_from.unit.chapter.id),
                    'name': donation.user.user.area_from.unit.chapter.chapter_name,
                    'code': donation.user.user.area_from.unit.chapter.chapter_code
                }
        
        return details
