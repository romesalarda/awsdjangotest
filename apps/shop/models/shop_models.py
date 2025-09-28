from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
import uuid

from .metadata_models import ProductMaterial, ProductCategory

class EventProduct(models.Model):
    '''
    Represents a product associated with a specific event.
    '''
    CATEGORY_CHOICES = [
        ('clothing', _('Clothing')),
        ('accessories', _('Accessories')),
        ('souvenirs', _('Souvenirs')),
        ('books', _('Books')),
        ('stationery', _('Stationery')),
        ('tech', _('Tech Items')),
        ('other', _('Other')),
    ]

    SIZE_CHOICES = [
        ('XS', _('Extra Small')),
        ('S', _('Small')),
        ('M', _('Medium')),
        ('L', _('Large')),
        ('XL', _('Extra Large')),
        ('XXL', _('Extra Extra Large')),
        ('One Size', _('One Size')),
    ]

    uuid = models.UUIDField(_("Product UUID"), default=uuid.uuid4, editable=False, primary_key=True)
    title = models.CharField(_("Product Name"), max_length=100)
    description = models.TextField(_("Product Description"), max_length=400, blank=True)
    extra_info = models.TextField(_("Additional Product Information"), max_length=400, blank=True, null=True)
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        verbose_name=_("Event Associated With This Product"),
        related_name="products"
    )
    
    price = models.FloatField(_("Product Cost (£)"))
    discount = models.FloatField(_("Product Discount (£)"), null=True, blank=True)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("Seller That Has Created This Product"),
        related_name="products"
    )

    # Simplified category as choice field instead of M2M
    category = models.CharField(_("Category"), max_length=20, choices=CATEGORY_CHOICES, default='other')
    
    # New fields to match frontend expectations
    stock = models.PositiveIntegerField(_("Stock Quantity"), default=0)
    featured = models.BooleanField(_("Featured Item"), default=False, help_text=_("Highlight this product in the store"))
    in_stock = models.BooleanField(_("In Stock"), default=True, help_text=_("Whether this item is available for purchase"))
    
    # Colors as JSON field for flexible color options (since there's no ProductColor model)
    colors = models.JSONField(_("Available Colors"), default=list, blank=True, help_text=_("List of available colors"))

    # Keep existing M2M relationships for backward compatibility
    categories = models.ManyToManyField(ProductCategory, blank=True, verbose_name=_("Categories"))
    materials = models.ManyToManyField(ProductMaterial, blank=True, verbose_name=_("Materials"))
    maximum_order_quantity = models.IntegerField(_("Maximum Order Quantity"), default=10)

    class Meta:
        ordering = ['title']
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def __str__(self) -> str:
        return f"{self.title} {self.event.event_code}"
    
    def save(self, *args, **kwargs):
        # Auto-set in_stock based on stock quantity
        self.in_stock = self.stock > 0
        
        # Ensure colors JSON field is a list if None
        if self.colors is None:
            self.colors = []
            
        super().save(*args, **kwargs)
    
    @property
    def name(self):
        """Alias for title to match frontend expectations"""
        return self.title
    
    @name.setter
    def name(self, value):
        self.title = value
    
    @property
    def primary_image_url(self):
        """Get the URL of the first product image"""
        first_image = self.images.first()
        return first_image.image.url if first_image else None
    
    @property
    def available_sizes(self):
        """Get list of available sizes for this product"""
        return [size.size for size in self.product_sizes.all()]


class EventCart(models.Model):
    """
    A shopping cart for products associated with a specific event.
    
    Represents a full order. Once a cart is approved and submitted, it should not be modified.
    """
    uuid = models.UUIDField(_("Cart UUID"), default=uuid.uuid4, editable=False, primary_key=True)
    order_reference_id = models.CharField(_("Order ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking order references
    
    total = models.FloatField(_("Total Cost"), default=0)
    shipping_cost = models.FloatField(_("Shipping Cost"), default=0)
    created = models.DateTimeField(_("Created At"), default=timezone.now)
    updated = models.DateTimeField(_("Last Updated"), auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        verbose_name=_("User")
    )
    approved = models.BooleanField(default=False, help_text=_("Flags if the cart has been approved"))
    submitted = models.BooleanField(default=False, help_text=_("Flags if the cart has been submitted"))
    active = models.BooleanField(default=True, help_text=_("Flags if the cart is active"))
    products = models.ManyToManyField(
        "shop.EventProduct",
        through="shop.EventProductOrder",
        related_name="carts",
        verbose_name=_("Products")
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name="carts",
        null=True,
        blank=True,
        verbose_name=_("Event")
    )
    notes = models.TextField(_("Cart Notes"), blank=True, null=True)
    shipping_address = models.TextField(_("Shipping Address"), blank=True, null=True)

    class Meta:
        ordering = ['-created']
        verbose_name = _("Event Cart")
        verbose_name_plural = _("Event Carts")

    def __str__(self) -> str:
        return f"CART{self.user.member_id} ({self.created:%Y-%m-%d %H:%M})"
    
    def save(self, *args, **kwargs):
        self.updated = timezone.now()
        
        if self.order_reference_id is None: # ORD<event-code>-<uuid[:10]>
            
            if self.uuid is None: # save if uuid not set yet
                super().save(*args, **kwargs)

            self.order_reference_id = f"ORD{self.event.event_code}-{str(self.uuid)[:10]}"

        return super().save(*args, **kwargs)
    
class EventProductOrder(models.Model):
    '''
    Product order within an event cart.
    '''
    # TODO: switch integer id to uuid?
    
    order_reference_id = models.CharField(_("Order ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking order references
    product = models.ForeignKey(EventProduct, on_delete=models.CASCADE, related_name="orders")
    cart = models.ForeignKey(EventCart, on_delete=models.CASCADE, related_name="orders")
    quantity = models.IntegerField(default=1)
    added = models.DateTimeField(_("Date Added to Cart"), default=timezone.now)
    price_at_purchase = models.FloatField(_("Price at Purchase (£)"), null=True, blank=True)
    discount_applied = models.FloatField(_("Discount Applied (£)"), null=True, blank=True)
    size = models.ForeignKey(
        'shop.ProductSize',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Product Size")
    )
    uses_size = models.BooleanField(default=False, help_text=_("Flags if a size is used for this product order"))
    time_added = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PURCHASED = "purchased", _("Purchased")
        CANCELLED = "cancelled", _("Cancelled")

    status = models.CharField(
        _("Order Status"),
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    # TODO: add field to check if the product can be changed. maybe add a new model to submit change requests?
    changeable = models.BooleanField(default=True, help_text=_("Flags if the product order can be changed"))
    
    change_requested = models.BooleanField(default=False, help_text=_("Flags if a change has been requested for this order"))
    change_reason = models.TextField(_("Reason for Change Request"), blank=True, null=True)
    admin_notes = models.TextField(_("Admin Notes"), blank=True, null=True, help_text=_("Notes for admin use only"))

    class Meta:
        ordering = ['-added']
        verbose_name = _("Event Product Order")
        verbose_name_plural = _("Event Product Orders")

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.order_reference_id is None: # ORD<event-code>-<cart-uuid[:10]>-<product-uuid[:10]>
            
            if self.cart is None or self.cart.uuid is None:
                raise ValueError("Cart must be set and saved before saving an order.")
            if self.product is None or self.product.uuid is None:
                raise ValueError("Product must be set and saved before saving an order.")
            self.order_reference_id = f"ORD{self.cart.event.event_code}-{str(self.cart.uuid)[:10]}-{str(self.product.uuid)[:10]}"
        return super().save(force_insert, force_update, using, update_fields)

    def __str__(self) -> str:
        return f"{self.product.title} ({self.cart.user.member_id})"
    
