from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder
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
    price = models.IntegerField(
        verbose_name=_("price (in pence)"),
        help_text=_("Store in smallest currency unit (e.g., pence for GBP, cents for USD)"),
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
        return f"{self.name} - {self.price / 100:.2f} {self.currency.upper()}"

class ProductPayment(models.Model):
    """
    Tracks a user's payment for products in a cart.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        SUCCEEDED = "SUCCEEDED", _("Succeeded")
        FAILED = "FAILED", _("Failed")

    payment_reference_id = models.CharField(_("Payment ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking payment references
    bank_reference = models.CharField(_("Bank Transfer Reference"), max_length=18, unique=True, blank=True, null=True) # short reference for bank transfers
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_payments")
    cart = models.ForeignKey(EventCart, on_delete=models.SET_NULL, null=True, blank=True, related_name="product_payments")
    
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
    amount = models.IntegerField(help_text=_("Amount in pence"))
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

    class Meta:
        verbose_name = _("Product Payment")
        verbose_name_plural = _("Product Payments")

    def mark_as_paid(self):
        self.status = self.PaymentStatus.SUCCEEDED
        self.save()
    
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
        instructions.append(f"Amount: £{self.amount / 100:.2f}")
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