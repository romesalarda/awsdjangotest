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

    # class Sizes(models.TextChoices): #TODO: Remove this and use ProductSize model instead
    #     EXTRA_SMALL = "XS", _("Extra Small")
    #     SMALL = "SM", _("Small")
    #     MEDIUM = "MD", _("Medium")
    #     LARGE = "LG", _("Large")
    #     EXTRA_LARGE = "XL", _("Extra Large")

    # size = models.CharField(
    #     _("Size"),
    #     max_length=5,
    #     choices=Sizes.choices,
    #     blank=True,
    #     null=True,
    #     default=Sizes.MEDIUM
    # )
    
    price = models.FloatField(_("Product Cost (£)"))
    discount = models.FloatField(_("Product Discount (£)"), null=True, blank=True)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("Seller That Has Created This Product"),
        related_name="products"
    )

    categories = models.ManyToManyField(ProductCategory, blank=True, verbose_name=_("Categories"))
    materials = models.ManyToManyField(ProductMaterial, blank=True, verbose_name=_("Materials"))

    class Meta:
        ordering = ['title']
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def __str__(self) -> str:
        return f"{self.title} {self.event.event_code}"


class EventCart(models.Model):
    """
    A shopping cart for products associated with a specific event.
    """
    uuid = models.UUIDField(_("Cart UUID"), default=uuid.uuid4, editable=False, primary_key=True)
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
    
class EventProductOrder(models.Model):
    '''
    Product order within an event cart.
    '''
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

    class Meta:
        ordering = ['-added']
        verbose_name = _("Event Product Order")
        verbose_name_plural = _("Event Product Orders")

    def __str__(self) -> str:
        return f"{self.product.title} ({self.cart.user.member_id})"
    
