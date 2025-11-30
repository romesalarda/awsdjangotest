from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import Coalesce, TruncDate
from collections import defaultdict
from datetime import datetime

from apps.events.models import Event, EventParticipant, EventPayment
from apps.shop.models import EventCart, EventProductOrder, ProductPayment, EventProduct, ProductPaymentMethod, OrderRefund


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
    
    @action(detail=True, methods=['get'], url_path='merch-payment-distribution')
    def merch_payment_distribution(self, request, pk=None):
        """
        Get MERCHANDISE ONLY payment status distribution by location
        Query params:
        - group_by: 'cluster', 'chapter', or 'area' (default: 'area')
        """
        try:
            event = Event.objects.get(id=pk)
            group_by = request.query_params.get('group_by', 'area')
            
            # Get all participants with their product payments
            participants = EventParticipant.objects.filter(event=event).select_related(
                'user__area_from__unit__chapter__cluster'
            ).prefetch_related('user__product_payments')
            
            distribution = defaultdict(lambda: {
                'total_participants': 0,
                'participants_with_orders': 0,
                'total_outstanding': 0,
                'total_verified': 0,
                'outstanding_amount': 0,
                'verified_amount': 0
            })
            
            for participant in participants:
                if not participant.user or not participant.user.area_from:
                    location_key = 'Unknown'
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
                
                # Product payments for this event only
                product_payments = participant.user.product_payments.filter(
                    cart__event=event
                )
                
                if product_payments.exists():
                    distribution[location_key]['participants_with_orders'] += 1
                
                for payment in product_payments:
                    # Verified: approved=True AND status=SUCCEEDED
                    if payment.approved and payment.status == ProductPayment.PaymentStatus.SUCCEEDED:
                        distribution[location_key]['total_verified'] += 1
                        distribution[location_key]['verified_amount'] += float(payment.amount or 0)
                    else:
                        distribution[location_key]['total_outstanding'] += 1
                        distribution[location_key]['outstanding_amount'] += float(payment.amount or 0)
            
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
            import traceback
            print(f"Error in merch_payment_distribution: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-revenue-timeline')
    def merch_revenue_timeline(self, request, pk=None):
        """
        Get merchandise revenue over time (daily aggregation)
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Get all product payments for this event, grouped by date
            payments_by_date = ProductPayment.objects.filter(
                cart__event=event
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                total_amount=Sum('amount'),
                verified_amount=Sum(
                    'amount',
                    filter=Q(approved=True, status=ProductPayment.PaymentStatus.SUCCEEDED)
                ),
                pending_amount=Sum(
                    'amount',
                    filter=Q(approved=False) | ~Q(status=ProductPayment.PaymentStatus.SUCCEEDED)
                ),
                payment_count=Count('id')
            ).order_by('date')
            
            timeline_data = [
                {
                    'date': item['date'].isoformat(),
                    'total_amount': float(item['total_amount'] or 0),
                    'verified_amount': float(item['verified_amount'] or 0),
                    'pending_amount': float(item['pending_amount'] or 0),
                    'payment_count': item['payment_count']
                }
                for item in payments_by_date
            ]
            
            return Response({
                'data': timeline_data,
                'summary': {
                    'total_days': len(timeline_data),
                    'total_revenue': sum(item['total_amount'] for item in timeline_data)
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in merch_revenue_timeline: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-payment-methods')
    def merch_payment_methods(self, request, pk=None):
        """
        Get breakdown of merchandise payments by payment method
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Get payment method breakdown
            payments = ProductPayment.objects.filter(
                cart__event=event
            ).select_related('method')
            
            method_stats = defaultdict(lambda: {
                'total_payments': 0,
                'verified_payments': 0,
                'pending_payments': 0,
                'total_amount': 0,
                'verified_amount': 0,
                'pending_amount': 0
            })
            
            for payment in payments:
                method_name = payment.method.get_method_display() if payment.method else 'Unknown'
                
                method_stats[method_name]['total_payments'] += 1
                method_stats[method_name]['total_amount'] += float(payment.amount or 0)
                
                if payment.approved and payment.status == ProductPayment.PaymentStatus.SUCCEEDED:
                    method_stats[method_name]['verified_payments'] += 1
                    method_stats[method_name]['verified_amount'] += float(payment.amount or 0)
                else:
                    method_stats[method_name]['pending_payments'] += 1
                    method_stats[method_name]['pending_amount'] += float(payment.amount or 0)
            
            # Convert to list
            chart_data = [
                {
                    'method': method,
                    **stats
                }
                for method, stats in sorted(method_stats.items())
            ]
            
            return Response({
                'data': chart_data,
                'summary': {
                    'total_methods': len(chart_data),
                    'total_payments': sum(item['total_payments'] for item in chart_data)
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in merch_payment_methods: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-cart-funnel')
    def merch_cart_funnel(self, request, pk=None):
        """
        Get cart completion funnel statistics
        """
        try:
            event = Event.objects.get(id=pk)
            
            total_carts = EventCart.objects.filter(event=event).count()
            carts_with_items = EventCart.objects.filter(
                event=event,
                orders__isnull=False
            ).distinct().count()
            submitted_carts = EventCart.objects.filter(event=event, submitted=True).count()
            approved_carts = EventCart.objects.filter(event=event, approved=True).count()
            paid_carts = EventCart.objects.filter(
                event=event,
                product_payments__approved=True,
                product_payments__status=ProductPayment.PaymentStatus.SUCCEEDED
            ).distinct().count()
            
            return Response({
                'funnel': [
                    {
                        'stage': 'Created',
                        'count': total_carts,
                        'percentage': 100
                    },
                    {
                        'stage': 'With Items',
                        'count': carts_with_items,
                        'percentage': round((carts_with_items / total_carts * 100), 2) if total_carts > 0 else 0
                    },
                    {
                        'stage': 'Submitted',
                        'count': submitted_carts,
                        'percentage': round((submitted_carts / total_carts * 100), 2) if total_carts > 0 else 0
                    },
                    {
                        'stage': 'Approved',
                        'count': approved_carts,
                        'percentage': round((approved_carts / total_carts * 100), 2) if total_carts > 0 else 0
                    },
                    {
                        'stage': 'Paid',
                        'count': paid_carts,
                        'percentage': round((paid_carts / total_carts * 100), 2) if total_carts > 0 else 0
                    }
                ],
                'summary': {
                    'conversion_rate': round((paid_carts / total_carts * 100), 2) if total_carts > 0 else 0,
                    'drop_off_rate': round(((total_carts - paid_carts) / total_carts * 100), 2) if total_carts > 0 else 0
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in merch_cart_funnel: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-orders')
    def merch_orders(self, request, pk=None):
        """
        Get all merchandise orders for the event with participant details
        Returns list of orders with cart, payment, and participant information
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Get all carts for this event with related data
            carts = EventCart.objects.filter(event=event, submitted=True).select_related(
                'user',
                'user__area_from',
                'event'
            ).prefetch_related(
                'orders__product',
                'orders__size',
                'product_payments__method'
            ).order_by('-created')
            
            orders_data = []
            
            for cart in carts:
                # Get participant information
                participant = EventParticipant.objects.filter(
                    event=event,
                    user=cart.user
                ).first()
                                
                # Get all product orders in this cart
                cart_orders = cart.orders.all()
                
                # Get payment info
                payments = cart.product_payments.all()
                payment_status = 'pending'
                payment_method = None
                total_paid = 0
                
                for payment in payments:
                    if payment.approved and payment.status == ProductPayment.PaymentStatus.SUCCEEDED:
                        payment_status = 'paid'
                        total_paid += float(payment.amount or 0)
                    if payment.method:
                        payment_method = payment.method.get_method_display()
                
                # Build items list
                items = []
                for order in cart_orders:
                    items.append({
                        'id': order.id,
                        'product_name': order.product.title,
                        'product_id': str(order.product.uuid),
                        'quantity': order.quantity,
                        'size': order.size.size if order.size else None,
                        'price': float(order.price_at_purchase or order.product.price),
                        'total': float(order.price_at_purchase or order.product.price) * order.quantity,
                        'status': order.status
                    })
                
                orders_data.append({
                    'cart_id': str(cart.uuid),
                    'order_reference_id': cart.order_reference_id,
                    'participant_id': participant.id if participant else None,
                    'participant_pax_id': participant.event_pax_id if participant else None,
                    'participant_name': f"{cart.user.first_name} {cart.user.last_name}",
                    'participant_email': cart.user.primary_email,
                    'participant_member_id': cart.user.member_id,
                    'area_from': cart.user.area_from.area_name if cart.user.area_from else 'Unknown',
                    'order_date': cart.created.isoformat(),
                    'status': payment_status,
                    'submitted': cart.submitted,
                    'approved': cart.approved,
                    'items': items,
                    'total': float(cart.total),
                    'shipping_cost': float(cart.shipping_cost),
                    'payment_method': payment_method,
                    'notes': cart.notes,
                    'created_via_admin': cart.created_via_admin
                })
            
            return Response({
                'orders': orders_data,
                'summary': {
                    'total_orders': len(orders_data),
                    'total_carts': carts.count(),
                    'total_revenue': sum(order['total'] for order in orders_data)
                }
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in merch_orders: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='merch-refund-statistics')
    def merch_refund_statistics(self, request, pk=None):
        """
        Get comprehensive refund statistics for the event
        Returns:
        - Total refund amount and count
        - Refund status breakdown
        - Refund reasons breakdown
        - Item-level refund statistics
        - Timeline of refunds
        """
        try:
            event = Event.objects.get(id=pk)
            
            # Get all refunds for this event
            refunds = OrderRefund.objects.filter(event=event).select_related(
                'cart', 'payment', 'user'
            )
            
            # Overall statistics
            total_refunds = refunds.count()
            total_refund_amount = refunds.aggregate(total=Sum('refund_amount'))['total'] or 0
            
            # Status breakdown
            status_breakdown = {}
            for status_choice in OrderRefund.RefundStatus.choices:
                status_code = status_choice[0]
                status_display = status_choice[1]
                count = refunds.filter(status=status_code).count()
                amount = refunds.filter(status=status_code).aggregate(total=Sum('refund_amount'))['total'] or 0
                status_breakdown[status_code] = {
                    'display': status_display,
                    'count': count,
                    'total_amount': float(amount)
                }
            
            # Refund reasons breakdown
            reason_breakdown = {}
            for reason_choice in OrderRefund.RefundReason.choices:
                reason_code = reason_choice[0]
                reason_display = reason_choice[1]
                count = refunds.filter(refund_reason=reason_code).count()
                amount = refunds.filter(refund_reason=reason_code).aggregate(total=Sum('refund_amount'))['total'] or 0
                if count > 0:  # Only include reasons that have been used
                    reason_breakdown[reason_code] = {
                        'display': reason_display,
                        'count': count,
                        'total_amount': float(amount)
                    }
            
            # Automatic vs Manual refunds
            automatic_count = refunds.filter(is_automatic_refund=True).count()
            manual_count = refunds.filter(is_automatic_refund=False).count()
            automatic_amount = refunds.filter(is_automatic_refund=True).aggregate(total=Sum('refund_amount'))['total'] or 0
            manual_amount = refunds.filter(is_automatic_refund=False).aggregate(total=Sum('refund_amount'))['total'] or 0
            
            # Item-level statistics (products that were refunded)
            refunded_cart_ids = refunds.values_list('cart_id', flat=True)
            refunded_orders = EventProductOrder.objects.filter(
                cart__uuid__in=refunded_cart_ids,
                status='refunded'
            ).select_related('product', 'size')
            
            # Group by product
            product_refunds = {}
            for order in refunded_orders:
                product_id = str(order.product.uuid)
                if product_id not in product_refunds:
                    product_refunds[product_id] = {
                        'product_name': order.product.title,
                        'product_id': product_id,
                        'total_quantity': 0,
                        'total_value': 0,
                        'sizes': {}
                    }
                
                product_refunds[product_id]['total_quantity'] += order.quantity
                product_refunds[product_id]['total_value'] += float(order.price_at_purchase * order.quantity)
                
                # Track sizes
                if order.size:
                    size_name = order.size.size
                    if size_name not in product_refunds[product_id]['sizes']:
                        product_refunds[product_id]['sizes'][size_name] = 0
                    product_refunds[product_id]['sizes'][size_name] += order.quantity
            
            # Timeline of refunds (last 30 days, grouped by day)
            from datetime import datetime, timedelta
            today = datetime.now().date()
            thirty_days_ago = today - timedelta(days=30)
            
            daily_refunds = refunds.filter(
                created_at__date__gte=thirty_days_ago
            ).annotate(
                refund_date=TruncDate('created_at')
            ).values('refund_date').annotate(
                count=Count('id'),
                total_amount=Sum('refund_amount')
            ).order_by('refund_date')
            
            timeline = []
            for day_data in daily_refunds:
                timeline.append({
                    'date': day_data['refund_date'].strftime('%Y-%m-%d'),
                    'count': day_data['count'],
                    'total_amount': float(day_data['total_amount'])
                })
            
            # Recent refunds (last 10)
            recent_refunds = refunds.order_by('-created_at')[:10].values(
                'id', 'refund_reference', 'refund_amount', 'status',
                'refund_reason', 'created_at', 'processed_at',
                'cart__order_reference_id', 'user__member_id'
            )
            
            recent_refunds_list = []
            for refund in recent_refunds:
                recent_refunds_list.append({
                    'id': refund['id'],
                    'refund_reference': refund['refund_reference'],
                    'amount': float(refund['refund_amount']),
                    'status': refund['status'],
                    'reason': refund['refund_reason'],
                    'created_at': refund['created_at'],
                    'processed_at': refund['processed_at'],
                    'cart_reference': refund['cart__order_reference_id'],
                    'user_member_id': refund['user__member_id']
                })
            
            return Response({
                'event_id': str(event.id),
                'event_name': event.name,
                'event_code': event.event_code,
                'summary': {
                    'total_refunds': total_refunds,
                    'total_refund_amount': float(total_refund_amount),
                    'automatic_refunds': {
                        'count': automatic_count,
                        'total_amount': float(automatic_amount)
                    },
                    'manual_refunds': {
                        'count': manual_count,
                        'total_amount': float(manual_amount)
                    }
                },
                'status_breakdown': status_breakdown,
                'reason_breakdown': reason_breakdown,
                'product_refunds': list(product_refunds.values()),
                'timeline': timeline,
                'recent_refunds': recent_refunds_list
            })
            
        except Event.DoesNotExist:
            return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print(f"Error in merch_refund_statistics: {str(e)}")
            print(traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


