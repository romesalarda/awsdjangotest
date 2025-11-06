from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core import validators
import uuid

from .event_models import EventResource, EventParticipant

class EventPaymentMethod(models.Model):
    """
    Payment method/configuration available for an event.
    """
    
    # TODO-FUTMIG: migrate from integer id to uuid field?
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class MethodType(models.TextChoices):
        STRIPE = "STRIPE", _("Stripe")
        BANK_TRANSFER = "BANK", _("Bank Transfer")
        CASH = "CASH", _("Cash / In-Person")
        PAYPAL = "PAYPAL", _("PayPal")
        OTHER = "OTHER", _("Other")

    event = models.ForeignKey(
        "Event",
        on_delete=models.CASCADE,
        related_name="payment_methods",
        verbose_name=_("event"),
    )

    method = models.CharField(
        max_length=20,
        choices=MethodType.choices,
        verbose_name=_("payment method"),
    )

    # Bank transfer details
    account_name = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("account name"))
    account_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("account number"))
    sort_code = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("sort code"))
    reference_instruction = models.TextField(max_length=100, blank=True, null=True, verbose_name=_("reference instruction"), help_text=_("E.g., 'Use your full name as reference'"))
    reference_example = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("reference example"), help_text=_("E.g., 'John Smith'"))
    important_information = models.TextField(blank=True, null=True, verbose_name=_("important information"), help_text=_("E.g., 'Payments may take 2-3 business days to process.'"))
    
    instructions = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("payment instructions"),
        help_text=_("E.g., 'Reference your full name when making the transfer'"),
    )
    fee_add_on = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name=_("additional fee"),
        help_text=_("Optional: additional fee (e.g., 2.50 for £2.50)"),
        validators=[validators.MinValueValidator(0)],
    )
    currency = models.CharField(max_length=10, default="gbp")
    percentage_fee_add_on = models.FloatField(
        default=0.0,
        verbose_name=_("percentage fee (%)"),
        help_text=_("Optional: percentage fee (e.g., 2.5 for 2.5%)"),
        validators=[validators.MinValueValidator(0.0)],
    )

    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Event Payment Method")
        verbose_name_plural = _("Event Payment Methods")

    def __str__(self):
        return f"{self.get_method_display()} ({self.event})"

class EventPaymentPackage(models.Model):
    """
    Represents different ticket/package options for an event.
    Example: £50 VIP (includes food + merch), £10 General Admission
    """
    
    # TODO-FUTMIG: migrate from integer id to uuid field?
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    event = models.ForeignKey(
        "Event",
        on_delete=models.CASCADE,
        related_name="payment_packages",
        verbose_name=_("event"),
    )

    name = models.CharField(max_length=100, verbose_name=_("package name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("package description"), help_text=_("E.g., short description of this package/ticket type"))
    package_date_starts = models.DateField(blank=True, null=True, verbose_name=_("package start date"), auto_now=True)
    package_date_ends = models.DateField(blank=True, null=True, verbose_name=_("package end date"))

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("price"),
        help_text=_("Price in pounds (e.g., 25.00 for £25.00)"),
    )
    discounted_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        verbose_name=_("discounted price"),
        help_text=_("Optional: discounted price in pounds (e.g., 20.00 for £20.00)"),
        default=0.00,
        validators=[validators.MinValueValidator(0)],
    )
    currency = models.CharField(max_length=10, default="gbp")

    capacity = models.IntegerField(
        blank=True,
        null=True,
        verbose_name=_("max capacity"),
        help_text=_("Optional: limit how many people can buy this package"),
    )
    
    resources = models.ManyToManyField(EventResource, blank=True, verbose_name=_("related package resources"))

    available_from = models.DateTimeField(blank=True, null=True, verbose_name=_("available from"))
    available_until = models.DateTimeField(blank=True, null=True, verbose_name=_("available until"))

    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    whats_included = models.TextField(blank=True, null=True, verbose_name=_("what's included"), help_text=_("E.g., 'Includes access to all sessions, meals, and a T-shirt.' Ensure items are separated by a comma"))
    main_package = models.BooleanField(default=False, verbose_name=_("is main package"), help_text=_("Mark this as the main package for the event (e.g., General Admission)"))
    
    class Meta:
        verbose_name = _("Event Payment Package")
        verbose_name_plural = _("Event Payment Packages")

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency.upper()}"

class EventPayment(models.Model):
    """
    Tracks a user's payment for an event
    """
    
    # TODO-FUTMIG: maybe migrate uuid for payments to be a uuid field instead of integer id?
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        SUCCEEDED = "SUCCEEDED", _("Succeeded")
        FAILED = "FAILED", _("Failed")

    user = models.ForeignKey(EventParticipant, on_delete=models.SET_NULL, related_name="participant_event_payments", null=True)
    event = models.ForeignKey("Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_payments")
    # used for customer reference and tracking
    event_payment_tracking_number = models.CharField(
        max_length=100, unique=True, verbose_name=_("payment tracking number"), help_text=_("Unique identifier for this payment (e.g., UUID or custom format)"),
        blank=True, null=True
        )
    bank_reference = models.CharField(_("Payment Reference"), max_length=18, unique=True, blank=True, null=True) # required for tracking payment references

    package = models.ForeignKey(
        "EventPaymentPackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("selected package"),
    )

    method = models.ForeignKey(
        "EventPaymentMethod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("payment method"),
    )

    stripe_payment_intent = models.CharField(max_length=255, unique=True, blank=True, null=True)

    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Amount in pounds (e.g., 30.00 for £30.00)")
    )
    currency = models.CharField(max_length=10, default="gbp")

    status = models.CharField(
        max_length=50,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True) 
    paid_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    verified = models.BooleanField(default=False, verbose_name=_("payment verified"), help_text=_("Set to true when payment is verified/confirmed"))
    
    def mark_as_paid(self):
        self.status = self.PaymentStatus.SUCCEEDED
        self.paid_at = timezone.now()
        self.save()
        
    def save(self, *args, **kwargs):
        if self.event_payment_tracking_number is None:
            self.event_payment_tracking_number = f"{self.event.event_code}-PAY-{uuid.uuid4()}".upper()
            
        if not self.bank_reference:
            self.bank_reference = f"{self.event.event_code[:5]}{str(uuid.uuid4())[:8].upper()}"
            
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Event Payment")
        verbose_name_plural = _("Event Payments")

    def __str__(self):
        return f"{self.user} - {self.event} - {self.get_status_display()}"


class ParticipantRefund(models.Model):
    """
    Tracks refunds owed to participants who have been cancelled/removed from events.
    Provides a clear audit trail for financial reconciliation.
    """
    
    class RefundStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending Processing")
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        PROCESSED = "PROCESSED", _("Refund Processed")
        CANCELLED = "CANCELLED", _("Refund Cancelled")
    
    # Core relationships
    participant = models.ForeignKey(
        EventParticipant,
        on_delete=models.CASCADE,
        related_name="refunds",
        verbose_name=_("participant")
    )
    event = models.ForeignKey(
        "Event",
        on_delete=models.CASCADE,
        related_name="participant_refunds",
        verbose_name=_("event")
    )
    
    # Refund tracking
    refund_reference = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("refund reference"),
        help_text=_("Unique identifier for this refund"),
        blank=True
    )
    
    # Financial details
    event_payment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name=_("event registration refund amount"),
        help_text=_("Amount to refund for event registration")
    )
    product_payment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name=_("merchandise refund amount"),
        help_text=_("Amount to refund for merchandise purchases")
    )
    total_refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("total refund amount"),
        help_text=_("Total amount to be refunded")
    )
    currency = models.CharField(max_length=10, default="gbp")
    
    # Status and tracking
    status = models.CharField(
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        verbose_name=_("refund status")
    )
    
    # Removal details
    removal_reason = models.TextField(
        verbose_name=_("reason for removal"),
        help_text=_("Reason provided when participant was removed from event")
    )
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_initiated",
        verbose_name=_("removed by")
    )
    
    # Refund processing details
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_processed",
        verbose_name=_("processed by")
    )
    processing_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("processing notes"),
        help_text=_("Internal notes about refund processing")
    )
    
    # Contact information (cached for reference)
    participant_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("participant email"),
        help_text=_("Email address at time of removal")
    )
    organizer_contact_email = models.EmailField(
        verbose_name=_("organizer contact email"),
        help_text=_("Email address for refund inquiries")
    )
    
    # Payment method details (for refund processing)
    original_payment_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("original payment method"),
        help_text=_("Payment method used for original transaction")
    )
    refund_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("refund method"),
        help_text=_("Method used to process refund")
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("updated at"))
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("processed at"),
        help_text=_("Date and time when refund was marked as processed")
    )
    
    def save(self, *args, **kwargs):
        # Auto-generate refund reference if not set
        if not self.refund_reference:
            event_code = self.event.event_code[:5] if hasattr(self.event, 'event_code') else 'EVT'
            self.refund_reference = f"{event_code}-REFUND-{uuid.uuid4()}".upper()
        
        # Auto-calculate total if not set
        if not self.total_refund_amount:
            self.total_refund_amount = self.event_payment_amount + self.product_payment_amount
        
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = _("Participant Refund")
        verbose_name_plural = _("Participant Refunds")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['event', 'status']),
            models.Index(fields=['participant']),
        ]
    
    def __str__(self):
        return f"{self.refund_reference} - £{self.total_refund_amount} - {self.get_status_display()}"

class DonationPayment(models.Model):
    """
    Tracks a donation, only can be made for a specific event, payed to a specific organisation
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        SUCCEEDED = "SUCCEEDED", _("Succeeded")
        FAILED = "FAILED", _("Failed")

    user = models.ForeignKey(EventParticipant, on_delete=models.SET_NULL, related_name="participant_event_payments", null=True)
    event = models.ForeignKey("Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_payments")
    # used for customer reference and tracking
    event_payment_tracking_number = models.CharField(
        max_length=100, unique=True, verbose_name=_("payment tracking number"), help_text=_("Unique identifier for this payment (e.g., UUID or custom format)"),
        blank=True, null=True
        )
    bank_reference = models.CharField(_("Payment Reference"), max_length=18, unique=True, blank=True, null=True) # required for tracking payment references

    method = models.ForeignKey(
        "EventPaymentMethod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("payment method"),
    )

    stripe_payment_intent = models.CharField(max_length=255, unique=True, blank=True, null=True)

    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Amount in pounds (e.g., 30.00 for £30.00)")
    )
    currency = models.CharField(max_length=10, default="gbp")

    status = models.CharField(
        max_length=50,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True) 
    paid_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    verified = models.BooleanField(default=False, verbose_name=_("payment verified"), help_text=_("Set to true when payment is verified/confirmed"))
    pay_to_event = models.BooleanField(default=True, verbose_name=_("pay to event"), help_text=_("pay this donation to the event being held"))
    
    def mark_as_paid(self):
        self.status = self.PaymentStatus.SUCCEEDED
        self.paid_at = timezone.now()
        self.save()
        
    def save(self, *args, **kwargs):
        if self.event_payment_tracking_number is None:
            self.event_payment_tracking_number = f"{self.event.event_code}-PAY-{uuid.uuid4()}".upper()
            
        if not self.bank_reference:
            self.bank_reference = f"{self.event.event_code[:5]}{str(uuid.uuid4())[:8].upper()}"
            
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Event Payment")
        verbose_name_plural = _("Event Payments")

    def __str__(self):
        return f"{self.user} - {self.event} - {self.get_status_display()}"