from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.shop.models.shop_models import EventProduct, EventCart, EventProductOrder

class ProductPaymentMethod(models.Model):
    """
    Payment method/configuration available for product purchases.
    """
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
        
    def save(self, force_insert = ..., force_update = ..., using = ..., update_fields = ...):
        if self.payment_reference_id is None: # PAY<cart-uuid[:10]>-<uuid[:10]>
            
            if self.cart is None or self.cart.uuid is None:
                raise ValueError("Cart must be set and saved before saving a payment.")
            
            if not self.pk: # only generate new uuid if this is a new object
                super().save(force_insert, force_update, using, update_fields) # save to get a primary key
            
            self.payment_reference_id = f"PAY{self.cart.uuid[:10]}-{str(self.pk).zfill(10)}"
        return super().save(force_insert, force_update, using, update_fields)

    def __str__(self):
        return f"{self.user} - {self.cart} - {self.get_status_display()}"