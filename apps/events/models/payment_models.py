from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core import validators

from .event_models import EventResource, EventParticipant

class EventPaymentMethod(models.Model):
    """
    Payment method/configuration available for an event.
    """

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
    iban = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("IBAN"))
    swift_bic = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("SWIFT/BIC"))

    instructions = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("payment instructions"),
        help_text=_("E.g., 'Reference your full name when making the transfer'"),
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

    price = models.IntegerField(
        verbose_name=_("price (in pence)"),
        help_text=_("Store in smallest currency unit (e.g., pence for GBP, cents for USD)"),
    )
    discounted_price = models.IntegerField(
        blank=True,
        verbose_name=_("discounted price (in pence)"),
        help_text=_("Optional: discounted price in smallest currency unit"),
        default=0,
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
        return f"{self.name} - {self.price:.2f} {self.currency.upper()}"

class EventPayment(models.Model):
    """
    Tracks a user's payment for an event
    """

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        SUCCEEDED = "SUCCEEDED", _("Succeeded")
        FAILED = "FAILED", _("Failed")

    user = models.ForeignKey(EventParticipant, on_delete=models.CASCADE)
    event = models.ForeignKey("Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_payments")

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

    amount = models.IntegerField(help_text=_("Amount in pence"))
    currency = models.CharField(max_length=10, default="gbp")

    status = models.CharField(
        max_length=50,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_as_paid(self):
        self.status = self.PaymentStatus.SUCCEEDED
        self.save()

    class Meta:
        verbose_name = _("Event Payment")
        verbose_name_plural = _("Event Payments")

    def __str__(self):
        return f"{self.user} - {self.event} - {self.get_status_display()}"
