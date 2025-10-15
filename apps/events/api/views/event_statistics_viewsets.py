from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import Coalesce
from collections import defaultdict

from apps.events.models import Event, EventParticipant, EventPayment
from apps.shop.models import EventCart, EventProductOrder, ProductPayment, EventProduct


class EventStatisticsViewSet(viewsets.ViewSet):
    """
    ViewSet for event statistics and analytics
    """
    
    @action(detail=True, methods=['get'], url_path='registration-distribution')
    def registration_distribution(self, request, pk=None):
        """
        Get registration distribution by location (cluster/chapter/area)
        Query params:
        - group_by: 'cluster', 'chapter', or 'area' (default: 'area')
        """
        try:
            event = Event.objects.get(id=pk)
            group_by = request.query_params.get('group_by', 'area')
            
            participants = EventParticipant.objects.filter(event=event).select_related(
                'user__area_from__unit__chapter__cluster'
            )
            
            distribution = defaultdict(lambda: {
                'total': 0,
                'confirmed': 0,
                'pending': 0,
                'cancelled': 0
            })
            
            for participant in participants:
                if not participant.user or not participant.user.area_from:
                    location_key = 'Unknown'
                    # continue
                else:
                    area_from = participant.user.area_from
                    if group_by == 'cluster':
                        location_key = area_from.unit.chapter.cluster.cluster_id if (
                            area_from.unit and 
                            area_from.unit.chapter and 
                            area_from.unit.chapter.cluster
                        ) else 'Unknown'
                    elif group_by == 'chapter':
                        location_key = area_from.unit.chapter.chapter_name if (
                            area_from.unit and 
                            area_from.unit.chapter
                        ) else 'Unknown'
                    else:  # area
                        location_key = area_from.area_name or 'Unknown'
                
                distribution[location_key]['total'] += 1
                
                status_lower = participant.status.lower() if participant.status else 'pending'
                if status_lower in distribution[location_key]:
                    distribution[location_key][status_lower] += 1
            
            # Convert to list format for chart
            chart_data = [
                {
                    'location': location,
                    **stats
                }
                for location, stats in sorted(distribution.items())
            ]
            
            return Response({
                'group_by': group_by,
                'data': chart_data,
                'total_participants': participants.count()
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in registration_distribution: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='payment-distribution')
    def payment_distribution(self, request, pk=None):
        """
        Get payment status distribution by location
        Includes both event payments and product payments
        Query params:
        - group_by: 'cluster', 'chapter', or 'area' (default: 'area')
        """
        try:
            event = Event.objects.get(id=pk)
            group_by = request.query_params.get('group_by', 'area')
            
            participants = EventParticipant.objects.filter(event=event).select_related(
                'user__area_from__unit__chapter__cluster'
            ).prefetch_related('participant_event_payments', 'user__product_payments')
            
            distribution = defaultdict(lambda: {
                'total_participants': 0,
                'event_payments_outstanding': 0,
                'event_payments_verified': 0,
                'product_payments_outstanding': 0,
                'product_payments_verified': 0,
                'total_outstanding': 0,
                'total_verified': 0,
                'outstanding_amount': 0,
                'verified_amount': 0
            })
            
            for participant in participants:
                if not participant.user or not participant.user.area_from:
                    location_key = 'Unknown'
                    continue
                else:
                    area_from = participant.user.area_from
                    if group_by == 'cluster':
                        location_key = area_from.unit.chapter.cluster.cluster_id if (
                            area_from.unit and 
                            area_from.unit.chapter and 
                            area_from.unit.chapter.cluster
                        ) else 'Unknown'
                    elif group_by == 'chapter':
                        location_key = area_from.unit.chapter.chapter_name if (
                            area_from.unit and 
                            area_from.unit.chapter
                        ) else 'Unknown'
                    else:  # area
                        location_key = area_from.area_name or 'Unknown'
                
                distribution[location_key]['total_participants'] += 1
                
                # Event payments
                event_payments = participant.participant_event_payments.filter(event=event)
                for payment in event_payments:
                    if payment.verified and payment.status == EventPayment.PaymentStatus.SUCCEEDED:
                        distribution[location_key]['event_payments_verified'] += 1
                        distribution[location_key]['verified_amount'] += float(payment.amount or 0)
                    else:
                        distribution[location_key]['event_payments_outstanding'] += 1
                        distribution[location_key]['outstanding_amount'] += float(payment.amount or 0)
                
                # Product payments
                product_payments = participant.user.product_payments.filter(
                    cart__event=event
                )
                for payment in product_payments:
                    if payment.approved and payment.status == ProductPayment.PaymentStatus.SUCCEEDED:
                        distribution[location_key]['product_payments_verified'] += 1
                        distribution[location_key]['verified_amount'] += float(payment.amount or 0)
                    else:
                        distribution[location_key]['product_payments_outstanding'] += 1
                        distribution[location_key]['outstanding_amount'] += float(payment.amount or 0)
                
                # Calculate totals
                distribution[location_key]['total_outstanding'] = (
                    distribution[location_key]['event_payments_outstanding'] + 
                    distribution[location_key]['product_payments_outstanding']
                )
                distribution[location_key]['total_verified'] = (
                    distribution[location_key]['event_payments_verified'] + 
                    distribution[location_key]['product_payments_verified']
                )
            
            # Convert to list format for chart
            chart_data = [
                {
                    'location': location,
                    **stats
                }
                for location, stats in sorted(distribution.items())
            ]
            
            return Response({
                'group_by': group_by,
                'data': chart_data
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-statistics')
    def merch_statistics(self, request, pk=None):
        """
        Get merchandise/product statistics for the event
        Returns:
        - Product-wise order counts
        - Size distribution
        - Revenue statistics
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Get all product orders for this event
            product_orders = EventProductOrder.objects.filter(
                cart__event=event
            ).select_related('product', 'size').values(
                'product__title',
                'product__uuid',
                'size__size'
            ).annotate(
                quantity=Sum('quantity'),
                total_orders=Count('id')
            )
            
            # Group by product
            products_data = {}
            for order in product_orders:
                product_name = order['product__title']
                if product_name not in products_data:
                    products_data[product_name] = {
                        'product_name': product_name,
                        'product_id': str(order['product__uuid']),
                        'total_quantity': 0,
                        'total_orders': 0,
                        'sizes': {}
                    }
                
                size_name = order['size__size'] or 'No Size'
                products_data[product_name]['total_quantity'] += order['quantity'] or 0
                products_data[product_name]['total_orders'] += order['total_orders']
                products_data[product_name]['sizes'][size_name] = order['quantity'] or 0
            
            # Get revenue statistics
            total_revenue = ProductPayment.objects.filter(
                cart__event=event,
                status=ProductPayment.PaymentStatus.SUCCEEDED,
                approved=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            pending_revenue = ProductPayment.objects.filter(
                cart__event=event,
                status__in=[ProductPayment.PaymentStatus.PENDING, ProductPayment.PaymentStatus.FAILED],
                approved=False
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Total carts
            total_carts = EventCart.objects.filter(event=event).count()
            submitted_carts = EventCart.objects.filter(event=event, submitted=True).count()
            approved_carts = EventCart.objects.filter(event=event, approved=True).count()
            
            return Response({
                'products': list(products_data.values()),
                'revenue': {
                    'total_revenue': float(total_revenue),
                    'pending_revenue': float(pending_revenue),
                    'total': float(total_revenue + pending_revenue)
                },
                'carts': {
                    'total': total_carts,
                    'submitted': submitted_carts,
                    'approved': approved_carts
                },
                'summary': {
                    'total_products_types': len(products_data),
                    'total_items_ordered': sum(p['total_quantity'] for p in products_data.values()),
                    'total_orders': sum(p['total_orders'] for p in products_data.values())
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='overall-summary')
    def overall_summary(self, request, pk=None):
        """
        Get overall event summary statistics
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Participant stats
            total_participants = EventParticipant.objects.filter(event=event).count()
            confirmed_participants = EventParticipant.objects.filter(
                event=event, 
                status__iexact='CONFIRMED'
            ).count()
            pending_participants = EventParticipant.objects.filter(
                event=event, 
                status__iexact='PENDING'
            ).count()
            
            # Payment stats
            event_revenue = EventPayment.objects.filter(
                event=event,
                status=EventPayment.PaymentStatus.SUCCEEDED,
                verified=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            event_pending = EventPayment.objects.filter(
                event=event,
                status__in=[EventPayment.PaymentStatus.PENDING, EventPayment.PaymentStatus.FAILED]
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            product_revenue = ProductPayment.objects.filter(
                cart__event=event,
                status=ProductPayment.PaymentStatus.SUCCEEDED,
                approved=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            product_pending = ProductPayment.objects.filter(
                cart__event=event,
                status__in=[ProductPayment.PaymentStatus.PENDING, ProductPayment.PaymentStatus.FAILED]
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Merch stats
            total_merch_orders = EventProductOrder.objects.filter(
                cart__event=event
            ).count()
            
            participants_with_merch = EventParticipant.objects.filter(
                event=event,
                user__carts__event=event
            ).distinct().count()
            
            return Response({
                'participants': {
                    'total': total_participants,
                    'confirmed': confirmed_participants,
                    'pending': pending_participants,
                    'with_merch': participants_with_merch
                },
                'revenue': {
                    'event_revenue': float(event_revenue),
                    'event_pending': float(event_pending),
                    'product_revenue': float(product_revenue),
                    'product_pending': float(product_pending),
                    'total_revenue': float(event_revenue + product_revenue),
                    'total_pending': float(event_pending + product_pending)
                },
                'merch': {
                    'total_orders': total_merch_orders,
                    'participants_with_orders': participants_with_merch
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
