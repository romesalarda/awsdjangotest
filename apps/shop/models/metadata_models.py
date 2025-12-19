from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid

class ProductCategory(models.Model):
    '''
    Model representing a product category.
    '''
    title = models.CharField(_("name of category"))
    description = models.TextField(_("category description"),max_length=400, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Product categories"

    def __str__(self) -> str:
        return self.title

class ProductMaterial(models.Model):
    '''
    Model representing a material that a product can be made of.
    '''
    title = models.CharField(_("name of material"))
    description = models.TextField(_("material description"),max_length=400, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Product materials"
    
    def __str__(self) -> str:
        return self.title

class ProductImage(models.Model):
    '''
    Model representing an image of a product. Many can be uploaded per product.
    '''
    uuid = models.UUIDField(_("product image uuid"), default=uuid.uuid4, editable=False, primary_key=True)
    image = models.ImageField(upload_to='event-product-images/')

    product = models.ForeignKey("shop.EventProduct", on_delete=models.CASCADE, verbose_name=_("product linked to"), related_name="images")

    def __str__(self) -> str:
        return self.image.name
    
class ProductSize (models.Model):
    '''
    Model representing a size option for products.
    Not all products will have all the sizes available. So you can link sizes to products as needed.
    '''
    product = models.ForeignKey("shop.EventProduct", on_delete=models.CASCADE, verbose_name=_("product linked to"), related_name="product_sizes")
    quantity = models.PositiveIntegerField(_("Quantity in stock"), default=0, help_text="Number of items available in this size.")
    
    class Sizes(models.TextChoices):
        EXTRA_SMALL = "XS", _("Extra Small")
        SMALL = "SM", _("Small")
        MEDIUM = "MD", _("Medium")
        LARGE = "LG", _("Large")
        EXTRA_LARGE = "XL", _("Extra Large")

    size = models.CharField(
        _("Size"),
        max_length=5,
        choices=Sizes.choices,
        default=Sizes.MEDIUM
    )
    price_modifier = models.DecimalField(_("Price Modifier (£)"), max_digits=10, decimal_places=2, default=0.00 , help_text="Additional cost for this size, e.g. larger sizes may cost more.")
    
    class Meta:
        verbose_name_plural = "Product sizes"
        unique_together = ('product', 'size')  # Prevent duplicate sizes for same product

    def __str__(self) -> str:
        return self.product.title + " - " + self.size
    
    def save(self, *args, **kwargs):
        """Validate quantity is non-negative before saving"""
        if self.quantity < 0:
            raise ValueError(f"Quantity cannot be negative. Attempted to set quantity to {self.quantity} for {self.product.title} - {self.size}")
        super().save(*args, **kwargs)
    
    def is_available(self):
        """Check if this size variant has stock available"""
        return self.quantity > 0
    
    def can_fulfill(self, requested_quantity):
        """
        Check if this size can fulfill the requested quantity.
        Returns: (can_fulfill: bool, available_quantity: int, error_message: str or None)
        """
        if requested_quantity <= 0:
            return False, self.quantity, "Requested quantity must be greater than 0."
        
        if self.quantity <= 0:
            return False, 0, f"Size {self.get_size_display()} is currently out of stock."
        
        if requested_quantity > self.quantity:
            return False, self.quantity, f"Only {self.quantity} available for size {self.get_size_display()}. You requested {requested_quantity}."
        
        return True, self.quantity, None
    
    def decrement_stock(self, quantity):
        """
        Atomically decrement stock for this size variant.
        Returns True if successful, raises ValidationError if insufficient stock.
        Uses select_for_update for pessimistic locking to prevent race conditions.
        """
        from django.db import transaction
        from django.core.exceptions import ValidationError
        
        if quantity <= 0:
            raise ValidationError(f"Cannot decrement stock by {quantity}. Quantity must be positive.")
        
        with transaction.atomic():
            # Lock the row to prevent concurrent modifications
            size_variant = ProductSize.objects.select_for_update().get(pk=self.pk)
            
            if size_variant.quantity < quantity:
                raise ValidationError(
                    f"Insufficient stock for {self.product.title} - {self.get_size_display()}. "
                    f"Requested: {quantity}, Available: {size_variant.quantity}"
                )
            
            size_variant.quantity -= quantity
            size_variant.save(update_fields=['quantity'])
            
            # Refresh current instance
            self.quantity = size_variant.quantity
            
        return True
    
    def increment_stock(self, quantity):
        """
        Atomically increment stock for this size variant (e.g., when removing from cart or refund).
        Returns True if successful.
        Uses select_for_update for pessimistic locking.
        """
        from django.db import transaction
        from django.core.exceptions import ValidationError
        
        if quantity <= 0:
            raise ValidationError(f"Cannot increment stock by {quantity}. Quantity must be positive.")
        
        with transaction.atomic():
            size_variant = ProductSize.objects.select_for_update().get(pk=self.pk)
            size_variant.quantity += quantity
            size_variant.save(update_fields=['quantity'])
            
            # Refresh current instance
            self.quantity = size_variant.quantity
            
        return True
    
    def get_final_price(self):
        """
        Calculate the final price for this size variant.
        Returns base product price + size-specific price modifier.
        """
        from decimal import Decimal
        base_price = Decimal(str(self.product.price))
        modifier = Decimal(str(self.price_modifier))
        return (base_price + modifier).quantize(Decimal('0.01'))