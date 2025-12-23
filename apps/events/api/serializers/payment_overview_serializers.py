"""
Payment Overview Serializers
Handles serialization for comprehensive payment analytics, revenue tracking, and timeline data.
"""

from rest_framework import serializers
from decimal import Decimal
from .payment_serializers import DonationPaymentSerializer, DonationPaymentListSerializer


class PaymentTimelineSerializer(serializers.Serializer):
    """
    Serializer for payment timeline data points.
    Used for rendering payment activity over time.
    """
    date = serializers.DateField()
    event_registrations = serializers.IntegerField(default=0)
    event_registration_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    merchandise_orders = serializers.IntegerField(default=0)
    merchandise_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    donations = serializers.IntegerField(default=0)
    donation_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    refunds = serializers.IntegerField(default=0)
    refund_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cumulative_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))


class PaymentMethodBreakdownSerializer(serializers.Serializer):
    """
    Serializer for payment method distribution.
    """
    method = serializers.CharField()
    method_display = serializers.CharField()
    count = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    percentage = serializers.FloatField()
    average_transaction = serializers.DecimalField(max_digits=10, decimal_places=2)


class LocationPaymentBreakdownSerializer(serializers.Serializer):
    """
    Serializer for payment breakdown by location (area/chapter/cluster).
    """
    location_id = serializers.CharField()
    location_name = serializers.CharField()
    location_type = serializers.CharField()  # 'area', 'chapter', 'cluster'
    total_participants = serializers.IntegerField()
    total_payments = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    verified_payments = serializers.IntegerField()
    verified_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_payments = serializers.IntegerField()
    pending_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_payment = serializers.DecimalField(max_digits=10, decimal_places=2)


class RevenueBreakdownSerializer(serializers.Serializer):
    """
    Serializer for detailed revenue breakdown.
    """
    # Event Registration Revenue
    event_registration_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    event_registration_count = serializers.IntegerField()
    event_registration_verified = serializers.DecimalField(max_digits=12, decimal_places=2)
    event_registration_pending = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Merchandise Revenue
    merchandise_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    merchandise_count = serializers.IntegerField()
    merchandise_verified = serializers.DecimalField(max_digits=12, decimal_places=2)
    merchandise_pending = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Donation Revenue
    donation_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    donation_count = serializers.IntegerField()
    donation_verified = serializers.DecimalField(max_digits=12, decimal_places=2)
    donation_pending = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Refunds
    total_refunds = serializers.DecimalField(max_digits=12, decimal_places=2)
    refund_count = serializers.IntegerField()
    processed_refunds = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_refunds = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Totals
    gross_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_verified_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_pending_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    currency = serializers.CharField(default='gbp')


class PaymentOverviewSerializer(serializers.Serializer):
    """
    Comprehensive payment overview for an event.
    Combines timeline, revenue breakdown, location analysis, and payment methods.
    """
    event_id = serializers.CharField()
    event_name = serializers.CharField()
    event_code = serializers.CharField()
    
    # Revenue summary
    revenue_breakdown = RevenueBreakdownSerializer()
    
    # Timeline data (for graphs)
    timeline_data = PaymentTimelineSerializer(many=True)
    
    # Payment method distribution
    payment_method_breakdown = PaymentMethodBreakdownSerializer(many=True)
    
    # Location breakdown
    location_breakdown = LocationPaymentBreakdownSerializer(many=True)
    
    # Quick stats
    total_participants = serializers.IntegerField()
    participants_paid = serializers.IntegerField()
    participants_pending = serializers.IntegerField()
    payment_completion_rate = serializers.FloatField()
    
    # Date range
    earliest_payment = serializers.DateTimeField(allow_null=True)
    latest_payment = serializers.DateTimeField(allow_null=True)
    
    generated_at = serializers.DateTimeField()


# DonationListSerializer and DonationDetailSerializer are now imported from payment_serializers.py
# Use DonationPaymentListSerializer for list views
# Use DonationPaymentSerializer for detail views


class DonationSummarySerializer(serializers.Serializer):
    """
    Serializer for donation summary statistics.
    """
    total_donations = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    verified_donations = serializers.IntegerField()
    verified_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_donations = serializers.IntegerField()
    pending_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_donation = serializers.DecimalField(max_digits=10, decimal_places=2)
    largest_donation = serializers.DecimalField(max_digits=10, decimal_places=2)
    donations_for_event = serializers.IntegerField()
    donations_for_event_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(default='gbp')
