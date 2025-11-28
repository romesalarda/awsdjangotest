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

    # SIZE_CHOICES = [
    #     ('XS', _('Extra Small')),
    #     ('S', _('Small')),
    #     ('M', _('Medium')),
    #     ('L', _('Large')),
    #     ('XL', _('Extra Large')),
    #     ('XXL', _('Extra Extra Large')),
    #     ('One Size', _('One Size')),
    # ]

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
    
    price = models.DecimalField(_("Product Cost (£)"), max_digits=10, decimal_places=2)
    discount = models.DecimalField(_("Product Discount (£)"), max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Role-based discount fields
    discount_for_service_team = models.BooleanField(
        _("Discount for Service Team"),
        default=False,
        help_text=_("Enable special discount for service team members")
    )
    service_team_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("service team discount type"),
        help_text=_("Type of discount for service team members")
    )
    service_team_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        verbose_name=_("service team discount value"),
        help_text=_("Discount value for service team (percentage or fixed amount)")
    )

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
    max_purchase_per_person = models.IntegerField(
        _("Maximum Purchase Per Person"), 
        default=-1,
        help_text=_("Maximum quantity a person can purchase across all orders. Set to -1 for unlimited.")
    )
    uses_sizes = models.BooleanField(
        _("Uses Sizes"),
        default=False,
        help_text=_("Indicates if this product has size options")
    )   
    only_service_team = models.BooleanField(    
        _("Only for Service Team"),
        default=False,
        help_text=_("If checked, only service team members can purchase this product")
    )   
    preview_date = models.DateTimeField(
        _("Preview Date"),
        null=True,
        blank=True,
        help_text=_("Date when product becomes visible but read-only. If not set, product is hidden until release_date.")
    )
    release_date = models.DateTimeField(
        _("Release Date"),
        null=True,
        blank=True,
        help_text=_("Date and time when the product becomes available for purchase")
    )
    end_date = models.DateTimeField(
        _("End Date"),
        null=True,
        blank=True,
        help_text=_("Date and time when the product is no longer available for purchase")
    )
    timezone = models.CharField(
        _("Event Timezone"),    
        max_length=50,
        default='UTC',
        help_text=_("Timezone for release and end dates")
    )   
    
    
    class Meta:
        ordering = ['title']
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def __str__(self) -> str:
        return f"{self.title} {self.event.event_code}"
    
    def save(self, *args, **kwargs):
        # Auto-set in_stock based on stock quantity
        
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
    
    def calculate_service_team_discount(self, original_price=None):
        """
        Calculate the service team discount amount for this product.
        
        Args:
            original_price (Decimal, optional): Price to calculate discount from. 
                                               Defaults to self.price if not provided.
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.discount_for_service_team or not self.service_team_discount_type or not self.service_team_discount_value:
            return Decimal('0')
        
        price = Decimal(str(original_price if original_price is not None else self.price))
        discount_value = Decimal(str(self.service_team_discount_value))
        
        if self.service_team_discount_type == 'PERCENTAGE':
            discount_amount = (price * discount_value) / Decimal('100')
        else:  # FIXED
            discount_amount = min(discount_value, price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def get_price_for_user(self, user):
        """
        Get the final price for a specific user, applying service team discount if applicable.
        Uses 4-tier cascading priority for service team members:
        1. Individual product discount (EventServiceTeamMember.product_discount) - Highest
        2. Role-based product discount (EventRoleDiscount.product_discount) - Best among all roles
        3. Product-specific discount (EventProduct.discount_for_service_team)
        4. Event-level product discount (Event.product_discount) - Final fallback
        
        Args:
            user: The user making the purchase
            
        Returns:
            Decimal: The final price after applicable discounts
        """
        from decimal import Decimal
        from apps.events.models import EventServiceTeamMember, EventRoleDiscount
        
        original_price = Decimal(str(self.price)).quantize(Decimal('0.01'))
        
        # Check if user is a service team member for this event
        try:
            service_team_member = EventServiceTeamMember.objects.get(
                user=user,
                event=self.event
            )
        except EventServiceTeamMember.DoesNotExist:
            # Not a service team member - return full price
            return original_price
        
        # Priority 1: Individual product discount
        if service_team_member.product_discount_type and service_team_member.product_discount_value:
            discount_amount = service_team_member.calculate_product_discount(original_price)
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return final_price
        
        # Priority 2: Role-based product discount (find the best discount among all roles)
        role_discounts = EventRoleDiscount.objects.filter(
            event=self.event,
            role__in=service_team_member.roles.all()
        )
        
        best_discount_amount = Decimal('0')
        for role_discount in role_discounts:
            if role_discount.has_product_discount:
                discount_amount = role_discount.calculate_product_discount(original_price)
                if discount_amount > best_discount_amount:
                    best_discount_amount = discount_amount
        
        if best_discount_amount > 0:
            final_price = max(original_price - best_discount_amount, Decimal('0')).quantize(Decimal('0.01'))
            return final_price
        
        # Priority 3: Product-specific discount
        if self.has_service_team_discount:
            discount_amount = self.calculate_service_team_discount()
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return final_price
        
        # Priority 4: Event-level product discount (final fallback for service team members)
        event = self.event
        if event.has_product_discount:
            discount_amount = event.calculate_product_discount(original_price)
            if discount_amount > 0:
                final_price = max(original_price - discount_amount, Decimal('0')).quantize(Decimal('0.01'))
                return final_price
        
        # No applicable discounts found
        return original_price
    
    @property
    def has_service_team_discount(self):
        """Check if this product has a service team discount configured."""
        return bool(
            self.discount_for_service_team and 
            self.service_team_discount_type and 
            self.service_team_discount_value and 
            self.service_team_discount_value > 0
        )
    
    def is_service_team_member(self, user):
        """Check if user is a service team member for this product's event."""
        from apps.events.models import EventServiceTeamMember
        return EventServiceTeamMember.objects.filter(
            event=self.event,
            user=user
        ).exists()
    
    def is_available_for_user(self, user):
        """
        Comprehensive availability check for a specific user.
        Returns tuple: (is_available: bool, reason: str or None, is_preview: bool)
        
        Checks:
        - Service team restriction (only_service_team)
        - Time-based availability (preview_date, release_date, end_date)
        - Stock availability
        - Event merch purchase windows
        """
        from django.utils import timezone
        now = timezone.now()
        
        # Check service team restriction first
        if self.only_service_team:
            if not self.is_service_team_member(user):
                return False, "This product is only available to service team members.", False
        
        # Check if product is in preview mode (visible but not purchasable)
        if self.preview_date and now >= self.preview_date:
            if self.release_date and now < self.release_date:
                return False, f"This product will be available for purchase on {self.release_date.strftime('%B %d, %Y at %I:%M %p')}.", True
        
        # Check if product hasn't been released yet (completely hidden)
        if self.release_date and now < self.release_date:
            if not self.preview_date or now < self.preview_date:
                return False, "This product is not yet available.", False
        
        # Check if product has ended (visible but read-only)
        if self.end_date and now > self.end_date:
            return False, "This product is no longer available for purchase.", True
        
        # Check event-level merch purchase permissions
        can_purchase, reason = self.event.can_purchase_merch(user)
        if not can_purchase:
            return False, reason, False
        
        # Check stock (if stock is 0, assume infinite - buy based on orders)
        if self.stock > 0 and self.stock <= 0:
            return False, "This product is currently out of stock.", False
        
        return True, None, False
    
    def is_purchasable(self, user):
        """
        Quick check if product can be added to cart right now.
        Returns tuple: (can_purchase: bool, reason: str or None)
        """
        is_available, reason, is_preview = self.is_available_for_user(user)
        
        if not is_available:
            return False, reason
        
        if is_preview:
            return False, reason
        
        return True, None
    
    def decrement_stock(self, quantity):
        """
        Atomically decrement product stock.
        Returns True if successful, False if insufficient stock.
        Only applies if stock > 0 (0 means infinite/made-to-order).
        """
        if self.stock == 0:  # Infinite stock
            return True
        
        from django.db.models import F
        from django.db import transaction
        
        with transaction.atomic():
            # Lock the row and refresh from DB
            product = EventProduct.objects.select_for_update().get(uuid=self.uuid)
            
            if product.stock < quantity:
                return False
            
            product.stock = F('stock') - quantity
            product.save(update_fields=['stock'])
            product.refresh_from_db()
            
            return True
    
    def increment_stock(self, quantity):
        """
        Atomically increment product stock (when removing from cart or cancelling).
        Only applies if stock was originally > 0.
        """
        if self.stock == 0:  # Was infinite stock, no need to increment
            return True
        
        from django.db.models import F
        from django.db import transaction
        
        with transaction.atomic():
            product = EventProduct.objects.select_for_update().get(uuid=self.uuid)
            product.stock = F('stock') + quantity
            product.save(update_fields=['stock'])
            product.refresh_from_db()
            
            return True


class EventCart(models.Model):
    """
    A shopping cart for products associated with a specific event.
    
    Represents a full order. Once a cart is approved and submitted, it should not be modified.
    """
    
    class CartStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        LOCKED = "locked", _("Locked - In Checkout")
        COMPLETED = "completed", _("Completed")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")
    
    uuid = models.UUIDField(_("Cart UUID"), default=uuid.uuid4, editable=False, primary_key=True)
    order_reference_id = models.CharField(_("Order ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking order references
    
    total = models.FloatField(_("Total Cost"), default=0)
    shipping_cost = models.DecimalField(_("Shipping Cost"), max_digits=10, decimal_places=2, default=0.00)
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
    created_via_admin = models.BooleanField(default=False, help_text=_("Flags if the cart was created by an admin/event organiser"))
    
    # New fields for cart locking and checkout
    cart_status = models.CharField(
        _("Cart Status"),
        max_length=20,
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        help_text=_("Current status of the cart")
    )
    locked_at = models.DateTimeField(
        _("Locked At"), 
        null=True, 
        blank=True,
        help_text=_("When the cart was locked for checkout")
    )
    lock_expires_at = models.DateTimeField(
        _("Lock Expires At"),
        null=True,
        blank=True,
        help_text=_("When the cart lock expires (typically 15 minutes)")
    )

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
    # TODO-FUTMIG: switch integer id to uuid
    
    order_reference_id = models.CharField(_("Order ID"), max_length=100, unique=True, blank=True, null=True) # required for tracking order references
    product = models.ForeignKey(EventProduct, on_delete=models.CASCADE, related_name="orders")
    cart = models.ForeignKey(EventCart, on_delete=models.CASCADE, related_name="orders")
    quantity = models.IntegerField(default=1)
    added = models.DateTimeField(_("Date Added to Cart"), default=timezone.now)
    price_at_purchase = models.DecimalField(_("Price at Purchase (£)"), max_digits=10, decimal_places=2, null=True, blank=True)
    discount_applied = models.DecimalField(_("Discount Applied (£)"), max_digits=10, decimal_places=2, null=True, blank=True)
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
    

class ProductPurchaseTracker(models.Model):
    """
    Tracks product purchases per user to enforce max_purchase_per_person limits globally.
    This ensures a user cannot exceed the purchase limit across multiple orders.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_purchase_trackers",
        verbose_name=_("User")
    )
    product = models.ForeignKey(
        EventProduct,
        on_delete=models.CASCADE,
        related_name="purchase_trackers",
        verbose_name=_("Product")
    )
    total_purchased = models.PositiveIntegerField(
        _("Total Purchased"),
        default=0,
        help_text=_("Total quantity purchased by this user for this product")
    )
    last_purchase_date = models.DateTimeField(
        _("Last Purchase Date"),
        auto_now=True,
        help_text=_("When the user last purchased this product")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-updated_at']
        verbose_name = _("Product Purchase Tracker")
        verbose_name_plural = _("Product Purchase Trackers")
        indexes = [
            models.Index(fields=['user', 'product']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.product.title} ({self.total_purchased})"
    
    @classmethod
    def get_user_purchased_quantity(cls, user, product):
        """
        Get total quantity across ALL orders (pending, verified, cancelled) for this user and product.
        This enforces max_purchase_per_person event-wide, preventing users from circumventing 
        limits by creating multiple carts or orders.
        """
        from django.db.models import Sum
        
        # Count all orders for this product, regardless of cart status
        total = EventProductOrder.objects.filter(
            product=product,
            cart__user=user,
            cart__event=product.event
        ).aggregate(
            total=Sum('quantity')
        )['total']
        
        return total or 0
    
    @classmethod
    def can_purchase(cls, user, product, quantity):
        """
        Check if user can purchase the specified quantity of this product.
        Counts ALL existing orders (pending, completed, cancelled) to enforce limits.
        Returns (can_purchase: bool, remaining_quantity: int, error_message: str)
        """
        # If product has no limit, allow purchase
        if product.max_purchase_per_person == -1:
            return True, float('inf'), None
        
        current_purchased = cls.get_user_purchased_quantity(user, product)
        remaining = product.max_purchase_per_person - current_purchased
        
        if remaining <= 0:
            return False, 0, f"You have already reached the maximum purchase limit ({product.max_purchase_per_person}) for this product across all orders."
        
        if quantity > remaining:
            return False, remaining, f"You can only purchase {remaining} more of this product (limit: {product.max_purchase_per_person}, current orders total: {current_purchased})."
        
        return True, remaining, None
    
    @classmethod
    def record_purchase(cls, user, product, quantity):
        """Record or update purchase tracking when order is completed"""
        tracker, created = cls.objects.get_or_create(
            user=user,
            product=product,
            defaults={'total_purchased': quantity}
        )
        if not created:
            tracker.total_purchased += quantity
            tracker.save()
        return tracker
