from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder
from django.utils import timezone
import uuid
class ProductPaymentMethod(models.Model):
    """
    Payment method/configuration available for product purchases.
    """
    # TODO-FUTMIG: migrate this
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class MethodType(models.TextChoices):
        STRIPE = "STRIPE", _("Stripe")
        BANK_TRANSFER = "BANK", _("Bank Transfer")
        CASH = "CASH", _("Cash / In-Person")
        PAYPAL = "PAYPAL", _("PayPal")
        OTHER = "OTHER", _("Other")

    method = models.CharField(
        max_length=20,
        choices=MethodType.choices,
        verbose_name=_("payment method"),
    )

    account_name = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("account name"))
    account_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("account number"))
    sort_code = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("sort code"))
    iban = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("IBAN"))
    swift_bic = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("SWIFT/BIC"))
    
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name="product_payment_methods",
        verbose_name=_("event"),
        blank=True,
        null=True,
    )

    instructions = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("payment instructions"),
        help_text=_("E.g., 'Reference your full name when making the transfer'"),
    )

    # Refund control fields
    supports_automatic_refunds = models.BooleanField(
        default=False,
        verbose_name=_("supports automatic refunds"),
        help_text=_("Enable for Stripe/PayPal. Disable for manual methods like bank transfer or cash.")
    )
    refund_contact_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("refund contact email"),
        help_text=_("Email address participants should contact for refund inquiries (leave blank to use secretariat)")
    )
    refund_processing_time = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("refund processing time"),
        help_text=_("E.g., '5-7 business days' - displayed to participants")
    )

    is_active = models.BooleanField(default=True, verbose_name=_("active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Product Payment Method")
        verbose_name_plural = _("Product Payment Methods")

    def __str__(self):
        return f"{self.get_method_display()} - {self.account_name or 'No Account Info'}"

class ProductPaymentPackage(models.Model):
    """
    Represents different package/bundle options for products (optional).
    I.e. A hoodie and t-shirt for £25, or just a t-shirt for £15, etc.
    """
    name = models.CharField(max_length=100, verbose_name=_("package name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("package description"))
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("price"),
        help_text=_("Price in pounds (e.g., 25.00 for £25.00)"),
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name="product_payment_packages",
        verbose_name=_("event"),
    )
    currency = models.CharField(max_length=10, default="gbp")
    products = models.ManyToManyField(EventProduct, blank=True, verbose_name=_("products in package"))
    available_from = models.DateTimeField(blank=True, null=True, verbose_name=_("available from"))
    available_until = models.DateTimeField(blank=True, null=True, verbose_name=_("available until"))
    is_active = models.BooleanField(default=True, verbose_name=_("active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Product Payment Package")
        verbose_name_plural = _("Product Payment Packages")

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency.upper()}"

class ProductPayment(models.Model):
    """
    Tracks a user's payment for products in a cart.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending") # when payment is initiated but not completed
        SUCCEEDED = "SUCCEEDED", _("Succeeded") # when payment is completed successfully
        FAILED = "FAILED", _("Failed") # when payment attempt fails due to technical/payment issues
        REFUND_PROCESSING = "REFUND_PROCESSING", _("Refund Processing") # when refund is initiated but not completed, happens when a payment is completed
        REFUNDED = "REFUNDED", _("Refunded") # when refund is completed
        CANCELLED = "CANCELLED", _("Cancelled") # if payment is voided before completion

    payment_reference_id = models.CharField(_("Payment ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking payment references
    bank_reference = models.CharField(_("Bank Transfer Reference"), max_length=18, unique=True, blank=True, null=True) # short reference for bank transfers
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="product_payments", null=True)
    cart = models.ForeignKey(EventCart, on_delete=models.SET_NULL, null=True, blank=True, related_name="product_payments")
    
    # Contact information for order fulfillment
    first_name = models.CharField(_("First Name"), max_length=100, blank=True)
    last_name = models.CharField(_("Last Name"), max_length=100, blank=True)
    email = models.EmailField(_("Email"), blank=True, help_text=_("Email for order confirmation and communication"))
    phone = models.CharField(_("Phone Number"), max_length=20, blank=True)
    
    package = models.ForeignKey(
        ProductPaymentPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("selected package"),
    )
    method = models.ForeignKey(
        ProductPaymentMethod,
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
    
    approved = models.BooleanField(default=False, help_text=_("Flags if the payment has been approved"))
    paid_at = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True, help_text=_("Internal notes about the payment"))

    class Meta:
        verbose_name = _("Product Payment")
        verbose_name_plural = _("Product Payments")

    def mark_as_paid(self):
        """Legacy method - use complete_payment() instead for full workflow."""
        self.status = self.PaymentStatus.SUCCEEDED
        self.save()
    
    def complete_payment(self, log_metadata=None):
        """
        Centralized payment completion logic used by both webhook and manual confirmation.
        Ensures consistent behavior across all payment success flows.
        
        This method handles:
        1. Updating payment status to SUCCEEDED
        2. Marking payment as approved
        3. Recording payment timestamp
        4. Updating cart status to COMPLETED
        5. Updating all order statuses to PURCHASED
        6. Recording purchase tracking for max purchase enforcement
        7. Deducting product stock
        8. Logging the transaction
        
        Args:
            log_metadata: Optional dict of metadata to include in payment log
            
        Returns:
            bool: True if successful, False if already completed
        """
        from apps.shop.models.shop_models import ProductPurchaseTracker
        from apps.shop.models.payments import ProductPaymentLog
        
        # Check if already completed (idempotency)
        if self.status == self.PaymentStatus.SUCCEEDED and self.approved:
            return False
        
        old_status = self.status
        
        # 1. Update payment status
        self.status = self.PaymentStatus.SUCCEEDED
        self.approved = True
        self.paid_at = timezone.now()
        self.save()
        
        # 2. Update cart status
        if self.cart:
            self.cart.cart_status = EventCart.CartStatus.COMPLETED
            self.cart.approved = True
            self.cart.save()
            
            # 3. Update order statuses and handle stock/tracking
            for order in self.cart.orders.all():
                # Update order status to PURCHASED
                order.status = EventProductOrder.Status.PURCHASED
                order.save()
                
                # 4. Record purchase tracking for max purchase enforcement
                ProductPurchaseTracker.record_purchase(
                    user=self.user,
                    product=order.product,
                    quantity=order.quantity
                )
                
                # 5. Deduct stock
                product = order.product
                product.stock = max(0, product.stock - order.quantity)
                product.save()
        
        # 6. Log the completion
        log_notes = "Payment completed successfully"
        if log_metadata and log_metadata.get('source'):
            log_notes = f"Payment completed via {log_metadata['source']}"
        
        ProductPaymentLog.log_action(
            payment=self,
            action='payment_succeeded',
            old_status=old_status,
            new_status=self.PaymentStatus.SUCCEEDED,
            notes=log_notes,
            metadata=log_metadata or {}
        )
        
        return True
    
    def get_bank_transfer_instructions(self):
        """
        Get formatted bank transfer instructions including the short reference ID.
        """
        if not self.method or self.method.method != ProductPaymentMethod.MethodType.BANK_TRANSFER:
            return None
            
        instructions = []
        # Use the short bank reference for transfers
        reference = self.bank_reference or self.payment_reference_id
        instructions.append(f"**Transfer Reference: {reference}**")
        instructions.append(f"Amount: £{self.amount:.2f}")
        instructions.append("")
        
        if self.method.account_name:
            instructions.append(f"Account Name: {self.method.account_name}")
        if self.method.account_number:
            instructions.append(f"Account Number: {self.method.account_number}")
        if self.method.sort_code:
            instructions.append(f"Sort Code: {self.method.sort_code}")
        if self.method.iban:
            instructions.append(f"IBAN: {self.method.iban}")
        if self.method.swift_bic:
            instructions.append(f"SWIFT/BIC: {self.method.swift_bic}")
            
        instructions.append("")
        instructions.append(f"⚠️ IMPORTANT: Use reference '{reference}' in your bank transfer.")
        instructions.append("This reference MUST be included for us to match your payment.")
        
        if self.method.instructions:
            instructions.append("")
            instructions.append("Additional Instructions:")
            instructions.append(self.method.instructions)
            
        return "\n".join(instructions)
        
    def save(self, force_insert = False, force_update = False, using = None, update_fields = None):
        if self.payment_reference_id is None:
            
            if self.cart is None or self.cart.uuid is None:
                raise ValueError("Cart must be set and saved before saving a payment.")
            
            if not self.pk: # only generate new uuid if this is a new object
                super().save(force_insert=True, using=using) # save to get a primary key

            # Generate standard payment reference ID
            self.payment_reference_id = f"PAY{str(self.cart.uuid)[:10]}-{str(self.pk).zfill(10)}"
            
            # Generate short bank reference for bank transfers (max 18 chars)
            if self.method and self.method.method == ProductPaymentMethod.MethodType.BANK_TRANSFER:
                from datetime import datetime
                # Format: YFC241001123 (YFC + YYMMDD + ID) = 12-15 characters
                date_str = datetime.now().strftime("%y%m%d")
                self.bank_reference = f"YFC{date_str}{str(self.pk)}"
                
        return super().save(force_insert=False, force_update=force_update, using=using, update_fields=update_fields)

    def __str__(self):
        return f"{self.user} - {self.cart} - {self.get_status_display()}"



class OrderRefund(models.Model):
    """
    Tracks refunds for merchandise orders (entire carts).
    Provides clear audit trail for product refund processing.
    Supports both automatic (Stripe) and manual (bank transfer) refunds.
    
    Key difference from ParticipantRefund:
    - OrderRefund: User-requested product/cart refunds only
    - ParticipantRefund: Full participant removal (event registration + products)
    """
    
    class RefundStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending Processing")
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        PROCESSED = "PROCESSED", _("Refund Processed")
        CANCELLED = "CANCELLED", _("Refund Cancelled")
        FAILED = "FAILED", _("Refund Failed")
    
    class RefundReason(models.TextChoices):
        CUSTOMER_REQUESTED = "CUSTOMER_REQUESTED", _("Customer Requested")
        WRONG_SIZE = "WRONG_SIZE", _("Wrong Size/Color")
        DAMAGED_ITEM = "DAMAGED_ITEM", _("Damaged Item")
        NOT_AS_DESCRIBED = "NOT_AS_DESCRIBED", _("Not As Described")
        DUPLICATE_ORDER = "DUPLICATE_ORDER", _("Duplicate Order")
        CHANGED_MIND = "CHANGED_MIND", _("Changed Mind")
        EVENT_CANCELLED = "EVENT_CANCELLED", _("Event Cancelled")
        ADMIN_DECISION = "ADMIN_DECISION", _("Administrative Decision")
        OTHER = "OTHER", _("Other")
    
    # Core relationships
    cart = models.ForeignKey(
        'shop.EventCart',
        on_delete=models.CASCADE,
        related_name="refunds",
        verbose_name=_("cart/order")
    )
    payment = models.ForeignKey(
        'shop.ProductPayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_refunds",
        verbose_name=_("original payment")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_refunds",
        verbose_name=_("customer")
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name="order_refunds",
        verbose_name=_("event")
    )
    
    # Link to parent ParticipantRefund if this order refund is part of a full participant removal
    participant_refund = models.ForeignKey(
        'events.ParticipantRefund',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_refunds",
        verbose_name=_("participant refund"),
        help_text=_("Parent participant refund if this is part of a full participant removal")
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
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("refund amount"),
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
    
    # Refund reason
    refund_reason = models.CharField(
        max_length=50,
        choices=RefundReason.choices,
        default=RefundReason.CUSTOMER_REQUESTED,
        verbose_name=_("refund reason")
    )
    reason_details = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("detailed reason"),
        help_text=_("Detailed explanation for the refund")
    )
    
    # Personnel tracking
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_refunds_initiated",
        verbose_name=_("initiated by")
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_refunds_processed",
        verbose_name=_("processed by")
    )
    processing_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("processing notes"),
        help_text=_("Internal notes about refund processing")
    )
    
    # Contact information (cached for reference)
    customer_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("customer email"),
        help_text=_("Email address at time of refund creation")
    )
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("customer name"),
        help_text=_("Full name at time of refund creation")
    )
    refund_contact_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("refund contact email"),
        help_text=_("Email address for refund inquiries (event organizer/secretariat)")
    )
    
    # Payment method details (for refund processing)
    original_payment_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("original payment method"),
        help_text=_("Payment method used for original transaction")
    )
    is_automatic_refund = models.BooleanField(
        default=False,
        verbose_name=_("automatic refund"),
        help_text=_("True if refund can be processed automatically via Stripe")
    )
    refund_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("refund method"),
        help_text=_("Method used to process refund (Stripe, Bank Transfer, etc.)")
    )
    
    # Stripe-specific fields
    stripe_payment_intent = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("original Stripe payment intent"),
        help_text=_("Original Stripe payment intent ID to refund")
    )
    stripe_refund_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("Stripe refund ID"),
        help_text=_("Stripe refund ID if processed through Stripe")
    )
    stripe_failure_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Stripe failure reason"),
        help_text=_("Reason if Stripe refund failed")
    )
    
    # NOTE: Bank account details should NEVER be stored in the database for security reasons.
    # Manual refunds should be processed outside the system and verified through admin notes.
    
    # Stock restoration tracking
    stock_restored = models.BooleanField(
        default=False,
        verbose_name=_("stock restored"),
        help_text=_("Whether product stock has been restored")
    )
    stock_restored_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("stock restored at")
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
    
    # Notification tracking
    customer_notified = models.BooleanField(
        default=False,
        verbose_name=_("customer notified"),
        help_text=_("Whether customer has been notified about the refund")
    )
    admin_notified = models.BooleanField(
        default=False,
        verbose_name=_("admin notified"),
        help_text=_("Whether admin/organizer has been notified")
    )
    
    def save(self, *args, **kwargs):
        # Auto-generate refund reference if not set
        if not self.refund_reference:
            event_code = self.event.event_code[:5] if self.event and hasattr(self.event, 'event_code') else 'SHOP'
            self.refund_reference = f"{event_code}-ORDREF-{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = _("Order Refund")
        verbose_name_plural = _("Order Refunds")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['event', 'status']),
            models.Index(fields=['cart']),
            models.Index(fields=['user']),
            models.Index(fields=['refund_reference']),
        ]
    
    def __str__(self):
        return f"{self.refund_reference} - £{self.refund_amount} - {self.get_status_display()}"
    
    def can_process_refund(self):
        """
        Check if refund can be processed based on eligibility rules.
        
        Returns:
            tuple: (can_process: bool, message: str)
        """
        from django.utils import timezone
        
        # Check if refund already processed or cancelled
        if self.status in [self.RefundStatus.PROCESSED, self.RefundStatus.CANCELLED]:
            return False, "Refund already processed or cancelled"
        
        # CRITICAL: Validate payment exists and is in correct state
        if not self.payment:
            return False, "Cannot process refund: No payment record found"
        
        # Only allow refunds for SUCCEEDED payments (payment verified and completed)
        if self.payment.status != ProductPayment.PaymentStatus.REFUND_PROCESSING:
            return False, f"Cannot process refund: Payment status is '{self.payment.get_status_display()}'. Only succeeded payments can be refunded."
        
        # Check if event has started (warning only, admins can override)
        if self.event and self.event.start_date and timezone.now() >= self.event.start_date:
            return True, "Warning: Event has started. Admin approval recommended."
        
        # Check refund deadline (warning only, admins can override)
        if self.event:
            refund_deadline = getattr(self.event, 'refund_deadline', None) or getattr(self.event, 'payment_deadline', None)
            if refund_deadline and timezone.now() > refund_deadline:
                return True, f"Warning: Refund deadline passed ({refund_deadline.strftime('%Y-%m-%d')}). Admin approval required."
        
        return True, "Refund can be processed"
    
    def restore_stock(self):
        """Restore product stock for all items in the cart"""
        if self.stock_restored:
            return False, "Stock already restored"
        
        try:
            from apps.shop.models import EventProductOrder
            orders = EventProductOrder.objects.filter(cart=self.cart)
            
            restored_items = []
            for order in orders:
                if order.product:
                    # Increment product stock
                    order.product.stock += order.quantity
                    order.product.save()
                    restored_items.append(f"{order.product.title} (+{order.quantity})")
            
            self.stock_restored = True
            self.stock_restored_at = timezone.now()
            self.save()
            
            return True, f"Stock restored for {len(restored_items)} items: {', '.join(restored_items)}"
        except Exception as e:
            return False, f"Failed to restore stock: {str(e)}"


class ProductPaymentLog(models.Model):
    """
    Audit log for all payment state changes and operations.
    Critical for security, debugging, and compliance.
    """
    payment = models.ForeignKey(
        ProductPayment,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name=_("payment")
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(
        max_length=50,
        verbose_name=_("action"),
        help_text=_("E.g., 'created', 'status_changed', 'approved', 'refunded'")
    )
    old_status = models.CharField(max_length=50, blank=True, null=True)
    new_status = models.CharField(max_length=50, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_logs",
        verbose_name=_("user who performed action")
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text=_("Additional context or details"))
    metadata = models.JSONField(default=dict, blank=True, help_text=_("Additional structured data"))

    class Meta:
        ordering = ['-timestamp']
        verbose_name = _("Product Payment Log")
        verbose_name_plural = _("Product Payment Logs")
        indexes = [
            models.Index(fields=['payment', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.payment.payment_reference_id} - {self.action} at {self.timestamp}"
    
    @classmethod
    def log_action(cls, payment, action, user=None, old_status=None, new_status=None, notes="", metadata=None, request=None):
        """Helper method to create a log entry"""
        log_data = {
            'payment': payment,
            'action': action,
            'old_status': old_status,
            'new_status': new_status,
            'amount': payment.amount,
            'user': user,
            'notes': notes,
            'metadata': metadata or {}
        }
        
        # Extract IP and user agent from request if provided
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                log_data['ip_address'] = x_forwarded_for.split(',')[0]
            else:
                log_data['ip_address'] = request.META.get('REMOTE_ADDR')
            log_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        return cls.objects.create(**log_data)
