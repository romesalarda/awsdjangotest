from datetime import timedelta
from django.db import models
from django.core import validators
from django.conf import settings
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from .location_models import (
    AreaLocation, ChapterLocation, EventVenue)
from .organsiation_models import Organisation
import uuid

MAX_LENGTH_EVENT_NAME_CODE = 5

class EventResource(models.Model):
    '''
    represents a resource e.g. a link to a further google form or a memo
    '''
    class ResourceType (models.TextChoices):
        LINK = "LINK", _("Link")
        PDF = "PDF", _("pdf")
        FILE = "FILE", _("File")
        PHOTO = "PHOTO", _("Photo")
        SOCIAL_MEDIA = "SOCIAL_MEDIA", _("Social Media")

    id = models.UUIDField(verbose_name=_("resource id"), default=uuid.uuid4, editable=False, primary_key=True)
    resource_name = models.CharField(verbose_name=_("public resource name"), max_length=200)
    resource_link = models.CharField(verbose_name=_("public resource link"), blank=True, null=True, validators=[validators.URLValidator()])
    resource_file = models.FileField(verbose_name=("file resource"), upload_to="public-event-file-resources", blank=True, null=True)
    image = models.FileField(verbose_name=("image resource"), upload_to="public-event-image-resources", blank=True, null=True)
    
    description = models.TextField(verbose_name=_("resource description"), max_length=500, blank=True, null=True)
    word_descriptor = models.TextField(verbose_name=_("word description"), max_length=100, blank=True, null=True, help_text=_("A word I.e. schedule or map"))

    created_at = models.DateTimeField(auto_now_add=True)
    public_resource = models.BooleanField(default=False)
    
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        verbose_name=_("resource added by"), null=True) # must be provided
    chapter_ownership = models.ForeignKey(
        ChapterLocation, on_delete=models.SET_NULL, 
        verbose_name=_("chapter that owns resource"), null=True, blank=True
        )

    # if used for events, can be gatekept until data is available
    release_date = models.DateTimeField(verbose_name=_("resource release date"), blank=True, null=True)
    expiry_date = models.DateTimeField(verbose_name=_("resource expiry date"), blank=True, null=True)
    
    def save(self, force_insert = ..., force_update = ..., using = ..., update_fields = ...):
        self.resource_name = slugify(self.resource_name.strip().capitalize()) if self.resource_name else None
        self.word_descriptor = slugify(self.word_descriptor.strip().capitalize()) if self.word_descriptor else None
        return super().save(force_insert, force_update, using, update_fields)
    

class Event(models.Model):
    '''
    Represents various types of events in the YFC Community
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class EventType(models.TextChoices):
        YOUTH_CAMP = "YOUTH_CAMP", _("YYC")
        CONFERENCE = "CONFERENCE", _("CNF")
        RETREAT = "RETREAT", _("RTR")
        WORKSHOP = "WORKSHOP", _("WKS")
        TRAINING = "TRAINING", _("TRN")
        PFO = "PFO", _("PFO")
        HOUSEHOLD = "HOUSEHOLD", _("HLD")
        FELLOWSHIP = "FELLOWSHIP", _("FLS")
        OTHER = "OTHER", _("OTH")
        
    class EventAreaType(models.TextChoices):
        AREA = "AREA", _("Area")
        UNIT = "UNIT", _("Unit")
        CLUSTER = "CLUSTER", _("Cluster") 
        NATIONAL = "NATIONAL", _("National")
        CONTINENTAL = "CONTINENTAL", _("Continental")
        INTERNATIONAL = "INTERNATIONAL", _("International")   
        
    # Event type and basic information
    event_type = models.CharField(_("event type"), max_length=20, choices=EventType.choices, default=EventType.YOUTH_CAMP)
    event_code = models.CharField(_("event code"), blank=True, null=True, 
                                  help_text=_("Event code that is shared around and for participant convenience. E.g. CNF26ANCRD - tells you it's a conference in 2026 with the name ANCHORED")
                                  ) # CNF26ANCRD
    
    description = models.TextField(verbose_name=_("event description"), blank=True, null=True) 
    sentence_description = models.CharField(
        verbose_name=_("sentence description"), blank=True, null=True, max_length=300,
        help_text=_("A brief one-sentence description of the event, for promotional purposes. E.g. A youth camp to anchor our faith in Christ.")
        ) 
    important_information = models.TextField(verbose_name=_("important information"), blank=True, null=True)
    what_to_bring = models.TextField(verbose_name=_("what to bring"), blank=True, null=True)
    landing_image = models.ImageField(        
        upload_to="event-landing-images/", 
        blank=True, 
        null=True,
        verbose_name=_("event landing image"))
    is_public = models.BooleanField(verbose_name=_("is event public"), default=False, null=True)
    
    name = models.CharField(_("event name"), max_length=200, null=True) # ANCHORED
    name_code = models.CharField( # simplified version of the name of the event
        _("event name code"), max_length=MAX_LENGTH_EVENT_NAME_CODE, 
        blank=True, null=True,
        validators=[
            validators.MaxLengthValidator(MAX_LENGTH_EVENT_NAME_CODE)
        ],
        help_text=_("Short code for the event name, used in generating the event code E.g. for ANCHORED event, use ANCRD")
        ) # ANCRD
    
    start_date = models.DateTimeField(_("event start date"), blank=True, null=True) # TODO: make this required - serializer end anyway
    end_date = models.DateTimeField(_("event end date"), blank=True, null=True) 
    
    # Location information
    area_type = models.CharField(verbose_name=_("area type"), max_length=20, choices=EventAreaType.choices, default=EventAreaType.AREA)
    venues = models.ManyToManyField(EventVenue, blank=True, verbose_name=_("venues involved"))
    areas_involved = models.ManyToManyField(AreaLocation, blank=True, related_name="involved_in_events") # community areas involved, either nationally or locally
    
    # Pastoral Event details
    number_of_pax = models.IntegerField(_("number of participants"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    theme = models.CharField(_("event theme"), max_length=200, blank=True, null=True)
    anchor_verse = models.CharField(_("anchor verse"), max_length=200, blank=True, null=True)
    age_range = models.CharField(_("age range"), max_length=20, blank=True, null=True, help_text=_("E.g. 11-30"))
    expected_attendees = models.IntegerField(_("expected attendees"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    maximum_attendees = models.IntegerField(_("maximum attendees"), blank=True, null=True, default=0, validators=[
        validators.MinValueValidator(0)
    ])
    # marks users that are able to view this event
    supervising_youth_heads = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,  
        verbose_name=_("youth chapter head supervisors"), related_name="supervised_events"
    )
    supervising_CFC_coordinators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        verbose_name=_("youth CFC coordinator supervisors"), related_name="cfc_supervised_events"
    )   
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_events",
        )

    # Service team
    service_team = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="EventServiceTeamMember", 
        through_fields=("event", "user"), 
        related_name="events_service_team", 
        blank=True
    )
    
    # important information
    resources = models.ManyToManyField(EventResource, blank=True, related_name="event_resources") # extra memos, photos promoting the event, etcs
    memo = models.ForeignKey(
        EventResource,
        verbose_name=_("main event memo"),
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name="event_memos"
        )
    notes = models.TextField(verbose_name=_("event notes"), blank=True, null=True)
    approved = models.BooleanField(verbose_name=_("event approved"), default=False) # Defines if even the one who created the event can even use it yet
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_events",
        verbose_name=_("approved by"),
        help_text=_("User who approved this event")
    )
    approved_at = models.DateTimeField(
        verbose_name=_("approval timestamp"),
        null=True,
        blank=True,
        help_text=_("When the event was approved")
    )
    approval_notes = models.TextField(
        verbose_name=_("approval notes"),
        blank=True,
        null=True,
        help_text=_("Notes from the approver to the event creator")
    )
    rejected = models.BooleanField(
        verbose_name=_("event rejected"),
        default=False,
        help_text=_("Whether this event has been rejected by an approver")
    )
    rejection_reason = models.TextField(
        verbose_name=_("rejection reason"),
        blank=True,
        null=True,
        help_text=_("Reason for rejecting this event")
    )
    
    # registration dates
    registration_open = models.BooleanField(verbose_name=_("is registration open"), default=False)
    registration_open_date = models.DateTimeField(verbose_name=_("registration open date"), blank=True, null=True, auto_now=True)
    registration_deadline = models.DateTimeField(verbose_name=_("registration deadline"), blank=True, null=True)
    payment_deadline = models.DateTimeField(verbose_name=_("payment deadline"), blank=True, null=True)
    
    # Refund policy
    refunds_enabled = models.BooleanField(
        verbose_name=_("refunds enabled"),
        default=False,
        help_text=_("Whether refunds are allowed for this event. If disabled, refund deadline is not applicable.")
    )
    refund_deadline = models.DateTimeField(
        verbose_name=_("refund deadline"),
        blank=True,
        null=True,
        help_text=_("Deadline for requesting refunds. Only applicable if refunds are enabled. If not set, defaults to payment_deadline.")
    )
    
    # Merchandise sale dates
    merch_sale_start_date = models.DateTimeField(
        verbose_name=_("merchandise sale start date"),
        blank=True,
        null=True,
        help_text=_("When merchandise becomes available for purchase. If not set, merch is available once registration opens.")
    )
    merch_sale_end_date = models.DateTimeField(
        verbose_name=_("merchandise sale end date"),
        blank=True,
        null=True,
        help_text=_("When merchandise sales close. If not set, defaults to payment_deadline or event end_date.")
    )
    merch_grace_period = models.BooleanField(
        verbose_name=_("merchandise grace period"),
        default=False,
        help_text=_("If enabled, users cannot create a new order while they have a pending/unverified order. They must wait for the current order to complete.")
    )
    
    # Legacy field - kept for backward compatibility
    product_purchase_deadline = models.DateTimeField(
        verbose_name=_("product purchase deadline"),
        blank=True,
        null=True,
        help_text=_("Deadline for purchasing products related to the event (deprecated - use merch_sale_end_date)")
    )
    
    class EventStatus(models.TextChoices):
        PLANNING = "PLANNING", _("Planning")
        CONFIRMED = "CONFIRMED", _("Confirmed")
        ONGOING = "ONGOING", _("Ongoing")
        COMPLETED = "COMPLETED", _("Completed")
        ARCHIVED = "ARCHIVED", _("Archived")
        
        CANCELLED = "CANCELLED", _("Cancelled")
        POSTPONED = "POSTPONED", _("Postponed") 
        
        REJECTED = "REJECTED", _("Rejected")
        PENDING_DELETION = "PENDING_DELETION", _("Pending Deletion")
        DELETED = "DELETED", _("Deleted")
        
    status = models.CharField(_("event status"), max_length=20, choices=EventStatus.choices, default=EventStatus.PLANNING)  
    
    auto_approve_participants = models.BooleanField(verbose_name=_("auto approve participants"), default=False)
    
    required_existing_id = models.BooleanField(default=False, help_text=_("Upon registration, the user must enter a specific ID that is linked to another system E.g. OGD"))
    format_verifier = models.CharField(max_length=100, blank=True, null=True, help_text=_("For requiring existing id, this can be used to match a given format I.e. %%%%-%%%%-%%%%"))
    existing_id_name = models.CharField(max_length=100, blank=True, null=True, help_text=_("existing name for this id E.g. Members-ID"))
    existing_id_description = models.TextField(max_length=500, blank=True, null=True)
    
    date_for_deletion = models.DateTimeField(
        verbose_name=_("date for deletion"),
        blank=True,
        null=True,
        help_text=_("If event is marked for deletion, this is the date when it will be permanently deleted.")
    )
    
    organisation = models.ForeignKey(
        Organisation, 
        on_delete=models.SET_NULL, 
        verbose_name=_("event organisation"),
        null=True,
        blank=True,
        help_text=_("defines the organisation attached to the event"),
        related_name="events"
        )
    force_participant_organisation = models.BooleanField(
        default=True, 
        help_text=_(
            "On registration, participants that register to this event will use the organisation defined above unless set otherwise. " + 
            "set to False to allow people from other organisations to define themelves on registration"
            ))
    
    # Event-level registration discount fields (for service team members only)
    registration_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("registration discount type"),
        help_text=_("Default discount type for event registration for service team members (can be overridden per role or individual)")
    )
    registration_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("registration discount value"),
        help_text=_("Default discount value for registration for service team members (percentage 0-100 or fixed amount in currency)")
    )
    
    # Event-level product discount fields (for service team members only)
    product_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("product discount type"),
        help_text=_("Default discount type for products for service team members (lowest priority fallback)")
    )
    product_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("product discount value"),
        help_text=_("Default discount value for products for service team members (percentage 0-100 or fixed amount)")
    )
    
    
    def save(self, *args, **kwargs):
        if not self.event_code:
            if not self.name_code:
                self.name_code = self.name.upper()[:MAX_LENGTH_EVENT_NAME_CODE]
            self.event_code = f"{self.get_event_type_display()}{str(self.start_date.year)}{self.name_code}"
                    
        return super().save(*args, **kwargs)
    
    def __str__(self):
        event_type = self.get_event_type_display()
        return f"{event_type}: {self.name or 'Unnamed Event'} ({self.start_date})" if self.start_date else f"{event_type}: {self.name or 'Unnamed Event'}"

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None
    
    def calculate_registration_discount(self, original_price):
        """
        Calculate the event-level discount amount for registration.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.registration_discount_type or not self.registration_discount_value:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.registration_discount_value))
        
        if self.registration_discount_type == 'PERCENTAGE':
            # Calculate percentage discount
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            # Use fixed discount amount (capped at original price)
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def get_discounted_registration_price(self, original_price):
        """
        Get the final registration price after applying event-level discount.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_registration_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))
    
    @property
    def has_registration_discount(self):
        """Check if this event has a default registration discount for service team members."""
        return bool(self.registration_discount_type and self.registration_discount_value and self.registration_discount_value > 0)
    
    def calculate_product_discount(self, original_price):
        """
        Calculate the event-level discount amount for products.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.product_discount_type or not self.product_discount_value:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.product_discount_value))
        
        if self.product_discount_type == 'PERCENTAGE':
            # Calculate percentage discount
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            # Use fixed discount amount (capped at original price)
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def get_discounted_product_price(self, original_price):
        """
        Get the final product price after applying event-level discount.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_product_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))
    
    @property
    def has_product_discount(self):
        """Check if this event has a default product discount for service team members."""
        return bool(self.product_discount_type and self.product_discount_value and self.product_discount_value > 0)
    
    def can_purchase_merch(self, user):
        """
        Check if a user can purchase merchandise for this event.
        
        Args:
            user: The user/participant attempting to purchase
            
        Returns:
            tuple: (can_purchase: bool, reason: str or None)
        """
        from django.utils import timezone
        now = timezone.now()
        
        # Check if event has ended
        if self.end_date and now > self.end_date:
            return False, "Event has ended. Merchandise sales are closed."
        
        # Check merch sale end date
        if self.merch_sale_end_date and now > self.merch_sale_end_date:
            return False, "Merchandise sales have ended for this event."
        
        # Check merch sale start date
        if self.merch_sale_start_date and now < self.merch_sale_start_date:
            return False, f"Merchandise sales start on {self.merch_sale_start_date.strftime('%B %d, %Y at %I:%M %p')}."
        
        # Check payment deadline
        if self.payment_deadline and now > self.payment_deadline:
            return False, "Payment deadline has passed. Merchandise sales are closed."
        
        # Check user's registration status
        try:
            participant = self.participants.get(user=user)
            
            # Cancelled registrations cannot purchase
            if participant.status == EventParticipant.ParticipantStatus.CANCELLED:
                return False, "Your registration has been cancelled. Please contact event organizers for assistance."
            
            # Only CONFIRMED participants can purchase merch
            if participant.status != EventParticipant.ParticipantStatus.CONFIRMED:
                return False, "Only confirmed participants can purchase merchandise. Please complete your registration and payment."
                
        except EventParticipant.DoesNotExist:
            return False, "You must be registered for this event to purchase merchandise."
        
        # Check grace period - if enabled, user cannot have pending orders
        if self.merch_grace_period:
            has_pending = self.has_pending_merch_order(user)
            if has_pending:
                return False, "You have a pending merchandise order. Please wait for it to be processed before creating a new order."
        
        return True, None
    
    def has_pending_merch_order(self, user):
        """
        Check if user has any pending/unverified merchandise orders for this event.
        Returns True if there are any active, unapproved, or unsubmitted carts.
        """
        from apps.shop.models import EventCart
        
        pending_carts = EventCart.objects.filter(
            event=self,
            user=user,
            active=True,
            cart_status__in=[EventCart.CartStatus.ACTIVE, EventCart.CartStatus.LOCKED]
        ).exclude(
            approved=True,
            submitted=True
        )
        
        return pending_carts.exists()
    
    def can_safely_delete(self):
        """
        Check if event can be safely deleted without losing critical data.
        
        Safe deletion criteria:
        - No participants registered
        - No event payments
        - No product payments/orders
        
        Returns:
            tuple: (can_delete: bool, reason: str or None, has_sensitive_data: bool)
        """
        from apps.shop.models import ProductPayment, EventCart
        
        # Check for participants
        participant_count = self.participants.count()
        if participant_count > 0:
            return False, f"Event has {participant_count} registered participant(s). Cannot delete without data loss.", True
        
        # Check for event payments
        payment_count = self.event_payments.count()
        if payment_count > 0:
            return False, f"Event has {payment_count} event payment record(s). Cannot delete without data loss.", True
        
        # Check for product payments
        product_payment_count = ProductPayment.objects.filter(cart__event=self).count()
        if product_payment_count > 0:
            return False, f"Event has {product_payment_count} product payment(s). Cannot delete without data loss.", True
        
        # Check for event carts (merchandise orders)
        cart_count = EventCart.objects.filter(event=self).count()
        if cart_count > 0:
            return False, f"Event has {cart_count} merchandise cart(s). Cannot delete without data loss.", True
        
        return True, None, False
    
    def can_be_cancelled(self):
        """
        Check if event can be cancelled.
        
        Cancellation criteria:
        - Event must not have started yet
        - Event cannot already be cancelled, completed, or deleted
        
        Returns:
            tuple: (can_cancel: bool, reason: str or None)
        """
        from django.utils import timezone
        now = timezone.now()
        
        # Check if event has already started
        if self.start_date and now >= self.start_date:
            return False, "Cannot cancel an event that has already started or is ongoing."
        
        # Check current status
        invalid_statuses = [
            self.EventStatus.CANCELLED,
            self.EventStatus.COMPLETED,
            self.EventStatus.DELETED,
            self.EventStatus.PENDING_DELETION
        ]
        
        if self.status in invalid_statuses:
            return False, f"Cannot cancel an event with status: {self.get_status_display()}"
        
        return True, None
    
    def can_be_postponed(self):
        """
        Check if event can be postponed.
        
        Postponement criteria:
        - Event must be approved or confirmed
        - Event must not have started yet
        - Event cannot already be cancelled, completed, or deleted
        
        Returns:
            tuple: (can_postpone: bool, reason: str or None)
        """
        from django.utils import timezone
        now = timezone.now()
        
        # Check if event has already started
        if self.start_date and now >= self.start_date:
            return False, "Cannot postpone an event that has already started or is ongoing."
        
        # Check if event was approved
        if not self.approved:
            return False, "Only approved events can be postponed."
        
        # Check current status
        invalid_statuses = [
            self.EventStatus.CANCELLED,
            self.EventStatus.COMPLETED,
            self.EventStatus.DELETED,
            self.EventStatus.PENDING_DELETION,
            self.EventStatus.REJECTED
        ]
        
        if self.status in invalid_statuses:
            return False, f"Cannot postpone an event with status: {self.get_status_display()}"
        
        return True, None
    
    def mark_for_deletion(self, deletion_date=None):
        """
        Mark event for deletion. Sets status to PENDING_DELETION.
        
        Args:
            deletion_date: Optional datetime when event should be permanently deleted
        
        Returns:
            bool: True if successfully marked
        """
        from django.utils import timezone
        from datetime import timedelta
        
        self.status = self.EventStatus.PENDING_DELETION
        self.is_public = False
        self.approved = False
        
        # Set deletion date if not provided (default 30 days from now)
        if deletion_date:
            self.date_for_deletion = deletion_date
        elif not self.date_for_deletion:
            self.date_for_deletion = timezone.now() + timedelta(days=30)
        
        self.save(update_fields=['status', 'date_for_deletion'])
        return True
    
    def mark_as_deleted(self):
        """
        Mark event as deleted (soft delete). Sets status to DELETED and makes it invisible to most users.
        Sets automatic deletion date to 30 days from now for database cleanup.
        This is used for events with sensitive data that cannot be immediately deleted.
        
        Returns:
            bool: True if successfully marked
        """
        from django.utils import timezone
        from datetime import timedelta
        
        self.status = self.EventStatus.DELETED
        self.is_public = False
        self.approved = False
        
        # Set automatic deletion date (30 days from now) if not already set
        if not self.date_for_deletion:
            self.date_for_deletion = timezone.now() + timedelta(days=30)
        
        self.save(update_fields=['status', 'date_for_deletion'])
        return True
    
    def cancel_event(self, reason=None):
        """
        Cancel the event. Sets status to CANCELLED.
        
        Args:
            reason: Optional cancellation reason
        
        Returns:
            bool: True if successfully cancelled
        """
        can_cancel, error_reason = self.can_be_cancelled()
        
        if not can_cancel:
            raise ValidationError(error_reason)
        
        self.status = self.EventStatus.CANCELLED
        
        # Store cancellation reason in notes if provided
        if reason:
            if self.notes:
                self.notes += f"\n\n[CANCELLED] {reason}"
            else:
                self.notes = f"[CANCELLED] {reason}"
        
        self.save(update_fields=['status', 'notes'])
        return True
    
    def postpone_event(self, reason=None):
        """
        Postpone the event. Sets status to POSTPONED.
        
        Args:
            reason: Optional postponement reason
        
        Returns:
            bool: True if successfully postponed
        """
        can_postpone, error_reason = self.can_be_postponed()
        
        if not can_postpone:
            raise ValidationError(error_reason)
        
        self.status = self.EventStatus.POSTPONED
        
        # Store postponement reason in notes if provided
        if reason:
            if self.notes:
                self.notes += f"\n\n[POSTPONED] {reason}"
            else:
                self.notes = f"[POSTPONED] {reason}"
        
        self.save(update_fields=['status', 'notes'])
        return True

class EventServiceTeamMember(models.Model):
    '''
    Represents the ST member of an event (through model)
    '''
    id = models.UUIDField(verbose_name=_("serivce team member id"), default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="event_memberships")  
    event = models.ForeignKey("Event", on_delete=models.CASCADE, 
                                  related_name="service_team_members")
    
    roles = models.ManyToManyField("EventRole", blank=True, related_name="service_team_members")  
    head_of_role = models.BooleanField(default=False)

    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="assigned_event_members"  
    ) 
    
    # Discount fields for service team members
    registration_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("discount type"),
        help_text=_("Type of discount for event registration")
    )
    registration_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("discount value"),
        help_text=_("Discount value (percentage or fixed amount in currency)")
    )
    product_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("product discount type"),
        help_text=_("Type of discount for products")
    )
    product_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("product discount value"),
        help_text=_("Discount value for products (percentage or fixed amount)")
    )

    class Meta:
        unique_together = ("user", "event") 
        verbose_name = _("Event Service Team Member")
        verbose_name_plural = _("Event Service Team Members")

    def __str__(self):
        return f"ST: {self.user}"
    
    def calculate_registration_discount(self, original_price):
        """
        Calculate the discount amount for event registration.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.registration_discount_type or not self.registration_discount_value:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.registration_discount_value))
        
        if self.registration_discount_type == 'PERCENTAGE':
            # Calculate percentage discount
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            # Use fixed discount amount (capped at original price)
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def calculate_product_discount(self, original_price):
        """
        Calculate the discount amount for products.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.product_discount_type or not self.product_discount_value:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.product_discount_value))
        
        if self.product_discount_type == 'PERCENTAGE':
            # Calculate percentage discount
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            # Use fixed discount amount (capped at original price)
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def get_discounted_registration_price(self, original_price):
        """
        Get the final price after applying registration discount.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_registration_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))
    
    def get_discounted_product_price(self, original_price):
        """
        Get the final price after applying product discount.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_product_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))
    
    @property
    def has_registration_discount(self):
        """Check if this service team member has a registration discount."""
        return bool(self.registration_discount_type and self.registration_discount_value and self.registration_discount_value > 0)
    
    @property
    def has_product_discount(self):
        """Check if this service team member has a product discount."""
        return bool(self.product_discount_type and self.product_discount_value and self.product_discount_value > 0)
    
class EventRole(models.Model):
    '''
    Event roles that can be assigned to service team members - Global use for reference
    '''
    id = models.UUIDField(verbose_name=_("event role id"), default=uuid.uuid4, editable=False, primary_key=True)

    class EventRoleTypes(models.TextChoices):
        ASSISTANT_TEAM_LEADER = "ASSISTANT_TEAM_LEADER", _("Assistant Team Leader")
        CAMP_SERVANT = "CAMP_SERVANT", _("Camp Servant")
        FACILITATOR = "FACILITATOR", _("Facilitator") 
        GAMES_MASTER = "GAMES_MASTER", _("Games Master")
        COUPLE_COORDINATOR = "COUPLE_COORDINATOR", _("Couple Coordinator") 
        SHARER = "SHARER", _("Sharer") 
        SPEAKER = "SPEAKER", _("Speaker") 
        TEAM_LEADER = "TEAM_LEADER", _("Team Leader") 
        WORSHIP_LEADER = "WORSHIP_LEADER", _("Worship Leader")
        TECH_SUPPORT = "TECH_SUPPORT", _("Tech Support") 
        YOUTH_OBSERVER = "YOUTH_OBSERVER", _("Youth Observer") 
        CFC_OBSERVER = "CFC_OBSERVER", _("CFC Observer") 
        CFC_HELPER = "CFC_HELPER", _("CFC Helper") 
        CFC_COORDINATOR = "CFC_COORDINATOR", _("Coordinator")
        SFC_HELPER = "SFC_HELPER", _("SFC Helper") 
        VOLUNTEER = "VOLUNTEER", _("Volunteer")
        ORGANIZER = "ORGANIZER", _("Organizer")
        # CONFERENCE LEVEL
        SECRETARIAT = "SECRETARIAT", _("Secretariat") 
        PROGRAMME = "PROGRAMME", _("Programme")
        PFO = "PFO", _("PFO")
        PRODUCTION = "PRODUCTION", _("Production")
        LOGISTICS = "LOGISTICS", _("Logistics")
        MUSIC_MINISTRY = "MUSIC_MINISTRY", _("Music Ministry") 
        LITURGY = "LITURGY", _("Liturgy")
        COMPETITIONS = "COMPETITIONS", _("Competitions")
        PROMOTIIONS = "PROMOTIONS", _("Promotions")
        DOCUMENTATION = "DOCUMENTATION", _("Documentation")      
        EVENT_HEADS = "EVENT_HEADS", _("Event_heads")
        GENERAL_SERVICES = "GENERAL_SERVICES", _("General Services")
        CATERING = "CATERING", _("Catering")
        
    role_name = models.CharField(
        _("role name"), max_length=50, choices=EventRoleTypes.choices,
        unique=True
    )
    
    description = models.TextField(_("role description"), blank=True, null=True)
    
    class Meta:
        verbose_name = _("Event Role")
        verbose_name_plural = _("Event Roles")
        ordering = ['role_name']
            
    def __str__(self):
        return self.get_role_name_display()

class EventRoleDiscount(models.Model):
    '''
    Represents role-based discounts for a specific event.
    Allows setting different discounts for each role on a per-event basis.
    E.g., Secretariat gets 20% off products in Event A, but 10% off in Event B.
    '''
    id = models.UUIDField(verbose_name=_("role discount id"), default=uuid.uuid4, editable=False, primary_key=True)
    
    event = models.ForeignKey(
        "Event", 
        on_delete=models.CASCADE, 
        related_name="role_discounts",
        verbose_name=_("event")
    )
    role = models.ForeignKey(
        "EventRole", 
        on_delete=models.CASCADE, 
        related_name="event_discounts",
        verbose_name=_("role")
    )
    
    # Registration discount fields
    registration_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("registration discount type"),
        help_text=_("Discount type for registration for this role in this event"),
    )
    registration_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("registration discount value"),
        help_text=_("Discount value for registration (percentage 0-100 or fixed amount)")
    )
    
    # Product discount fields
    product_discount_type = models.CharField(
        max_length=20,
        choices=[('PERCENTAGE', 'Percentage'), ('FIXED', 'Fixed Amount')],
        blank=True,
        null=True,
        verbose_name=_("product discount type"),
        help_text=_("Discount type for products for this role in this event")
    )
    product_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        validators=[validators.MinValueValidator(0)],
        verbose_name=_("product discount value"),
        help_text=_("Discount value for products (percentage or fixed amount)")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("event", "role")
        verbose_name = _("Event Role Discount")
        verbose_name_plural = _("Event Role Discounts")
        ordering = ['event', 'role']
    
    def __str__(self):
        return f"{self.role.get_role_name_display()} discount for {self.event.name}"
    
    @property
    def has_registration_discount(self):
        """Check if this role has a registration discount for this event."""
        return bool(self.registration_discount_type and self.registration_discount_value and self.registration_discount_value > 0)
    
    @property
    def has_product_discount(self):
        """Check if this role has a product discount for this event."""
        return bool(self.product_discount_type and self.product_discount_value and self.product_discount_value > 0)
    
    def calculate_registration_discount(self, original_price):
        """
        Calculate the discount amount for event registration.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.has_registration_discount:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.registration_discount_value))
        
        if self.registration_discount_type == 'PERCENTAGE':
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def calculate_product_discount(self, original_price):
        """
        Calculate the discount amount for products.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The discount amount to subtract from the original price
        """
        from decimal import Decimal
        
        if not self.has_product_discount:
            return Decimal('0')
        
        original_price = Decimal(str(original_price))
        discount_value = Decimal(str(self.product_discount_value))
        
        if self.product_discount_type == 'PERCENTAGE':
            discount_amount = (original_price * discount_value) / Decimal('100')
        else:  # FIXED
            discount_amount = min(discount_value, original_price)
        
        return discount_amount.quantize(Decimal('0.01'))
    
    def get_discounted_registration_price(self, original_price):
        """
        Get the final price after applying registration discount.
        
        Args:
            original_price (Decimal): The original registration price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_registration_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))
    
    def get_discounted_product_price(self, original_price):
        """
        Get the final price after applying product discount.
        
        Args:
            original_price (Decimal): The original product price
            
        Returns:
            Decimal: The final price after discount
        """
        from decimal import Decimal
        
        discount = self.calculate_product_discount(original_price)
        final_price = Decimal(str(original_price)) - discount
        return max(final_price, Decimal('0')).quantize(Decimal('0.01'))

# * EVENT PARTICIPANT MODELS
    
class EventParticipant(models.Model):
    '''
    Represents participants in events of various sizes
    '''
    class ParticipantStatus(models.TextChoices):
        REGISTERED = "REGISTERED", _("Registered")
        CONFIRMED = "CONFIRMED", _("Confirmed")
        ATTENDED = "ATTENDED", _("Attended")
        CANCELLED = "CANCELLED", _("Cancelled")
        WAITLISTED = "WAITLISTED", _("Waitlisted")
    
    class ParticipantType(models.TextChoices):
        PARTICIPANT = "PARTICIPANT", _("Participant")
        SERVICE_TEAM = "SERVICE_TEAM", _("Service_team")
        OBSERVER = "OBSERVER", _("Observer")
        GUEST = "GUEST", _("Guest")
        VISITOR = "VISITOR", _("Visitor")
        SPEAKER = "SPEAKER", _("Speaker")
        VOLUNTEER = "VOLUNTEER", _("Volunteer")
    
    # essential info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # unique participant ID for the event - basically their reference number
    # event code + unique uuid of this participant object
    event_pax_id = models.CharField(verbose_name=_("Participant ID"), blank=True, null=True, unique=True)
    secondary_reference_id = models.CharField(
        verbose_name=_("backup reference id"), 
        blank=True, null=True, 
        help_text=_("acts as a secondary id option and is good for backwards compatibility for exisiting database references"))

    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="participants")
    
    # if the user already exists in the database, then default to use this 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name="event_participations", blank=True, null=True)    
    # Participant meta information
    participant_type = models.CharField(_("participant type"), max_length=20, 
                                      choices=ParticipantType.choices, default=ParticipantType.PARTICIPANT)
    status = models.CharField(_("status"), max_length=20, 
                             choices=ParticipantStatus.choices, default=ParticipantStatus.REGISTERED)
    
    # Registration details
    registration_date = models.DateTimeField(_("registration date"), auto_now_add=True)
    confirmation_date = models.DateTimeField(_("confirmation date"), blank=True, null=True)
    attended_date = models.DateTimeField(_("attended date"), blank=True, null=True)
    
    # Consent Details
    media_consent = models.BooleanField(default=False)
    data_consent = models.BooleanField(default=False)
    understood_registration = models.BooleanField(default=False)
    terms_and_conditions_consent = models.BooleanField(default=False)
    news_letter_consent = models.BooleanField(default=False)

    # Payment information (if applicable)
    paid_amount = models.DecimalField(_("paid amount"), max_digits=10, decimal_places=2, default=0.00, validators=[validators.MinValueValidator(0)])
    payment_date = models.DateTimeField(_("most recent payment date"), blank=True, null=True)
    
    notes = models.TextField(_("notes"), blank=True, null=True)
    verified = models.BooleanField(verbose_name=_("participant approved"), default=False) # set to true when payments paid and they are approved to attend
    
    accessibility_requirements = models.TextField(_("accessibility requirements"), blank=True, null=True)
    special_requests = models.TextField(_("special requests"), blank=True, null=True)
    
    organisation = models.ForeignKey(
        Organisation, 
        on_delete=models.SET_NULL, 
        verbose_name=_("event organisation"),
        null=True,
        blank=True,
        help_text=_("defines the organisation attached to the event"),
        related_name="event_participants"
        )
    
    allowed_to_buy_products = models.BooleanField(  
        verbose_name=_("allowed to buy products"), 
        default=True,
        help_text=_("Defines if this participant is allowed to purchase products related to the event")
    )
    is_visible = models.BooleanField(
        verbose_name=_("is visible"),
        default=True,
        help_text=_("Defines if this participant is visible in participant lists")
    ) # when a user is banned or blacklisted from an event, set this to false to hide them from lists, delete later if needed
    
    class Meta:
        verbose_name = _("Event Participant")
        verbose_name_plural = _("Event Participants")
        ordering = ['registration_date']
        
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_event_user_participation"
            ),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.event} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.id:
            super().save(*args, **kwargs)
            
        if not self.event_pax_id:
            self.event_pax_id = f"{self.event.event_code}-{self.id}".upper()
            while EventParticipant.objects.filter(event_pax_id=self.event_pax_id).exists():
                self.id = uuid.uuid4()
                self.event_pax_id = f"{self.event.event_code}-{self.id}".upper()
            if len(self.event_pax_id) > 20:
                self.event_pax_id = self.event_pax_id[:20]  
        super().save(*args, **kwargs)
        
    @property
    def total_outstanding(self):
        from apps.shop.models import EventCart
        
        carts = EventCart.objects.filter(event=self.event, user=self.user, approved=False, submitted=False)
        event_payment = self.event.event_payments.filter(verified=False).first()
        total = sum(cart.total_amount for cart in carts) + (event_payment.amount if event_payment else 0)
        return total
    

# EVENT PROPER MODELS

class EventTalk(models.Model):
    '''
    !NOT IN USE
    '''
    class TalkType(models.TextChoices):
        TALK = "TALK", _("Talk")
        SHARING = "SHARING", _("Sharing")
        WORKSHOP = "WORKSHOP", _("Workshop")
        BREAKOUT = "BREAKOUT", _("Breakout Session")
        PLENARY = "PLENARY", _("Plenary Session")
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="talks")
    
    # Talk information
    title = models.CharField(_("talk title"), max_length=200)
    talk_type = models.CharField(_("talk type"), max_length=20, choices=TalkType.choices, default=TalkType.TALK)
    description = models.TextField(_("description"), blank=True, null=True)
    objective = models.TextField(_("objective"), blank=True, null=True)
    
    # Scheduling
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(_("end time"))
    duration_minutes = models.IntegerField(_("duration in minutes"), validators=[validators.MinValueValidator(1)])
    
    # Speaker information
    speaker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                               null=True, blank=True, related_name="event_talks")
    speaker_bio = models.TextField(_("speaker bio"), blank=True, null=True)
    
    # Location
    venue = models.CharField(_("venue"), max_length=200, blank=True, null=True)
    room = models.CharField(_("room"), max_length=100, blank=True, null=True)
    
    # Resources
    slides_url = models.URLField(_("slides URL"), blank=True, null=True)
    handout_url = models.URLField(_("handout URL"), blank=True, null=True)
    video_url = models.URLField(_("video URL"), blank=True, null=True)
    
    # Status
    is_published = models.BooleanField(_("is published"), default=True)
    
    class Meta:
        verbose_name = _("Event Talk")
        verbose_name_plural = _("Event Talks")
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.title} - {self.event.name}"

class EventWorkshop(models.Model):
    '''
    !NOT IN USE
    '''
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="workshops")
    
    # Workshop information
    title = models.CharField(_("workshop title"), max_length=200)
    description = models.TextField(_("description"))
    objectives = models.TextField(_("learning objectives"))
    
    # Scheduling
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(_("end time"))
    duration_minutes = models.IntegerField(_("duration in minutes"), validators=[validators.MinValueValidator(1)])
    
    # Facilitators (workshop leader, etc)
    facilitators = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="facilitated_workshops", blank=True)
    primary_facilitator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                           null=True, blank=True, related_name="primary_workshops")
    
    # Capacity
    max_participants = models.IntegerField(_("maximum participants"), validators=[validators.MinValueValidator(1)])
    min_participants = models.IntegerField(_("minimum participants"), default=1, 
                                          validators=[validators.MinValueValidator(1)])
    
    # Location
    venue = models.CharField(_("venue"), max_length=200, blank=True, null=True)
    room = models.CharField(_("room"), max_length=100, blank=True, null=True)
    
    # Requirements
    prerequisites = models.TextField(_("prerequisites"), blank=True, null=True)
    materials_needed = models.TextField(_("materials needed"), blank=True, null=True)
    participant_preparation = models.TextField(_("participant preparation"), blank=True, null=True)
    
    # Resources
    resource_materials = models.TextField(_("resource materials"), blank=True, null=True)
    handout_url = models.URLField(_("handout URL"), blank=True, null=True)
    
    # Status
    is_published = models.BooleanField(_("is published"), default=True)
    is_full = models.BooleanField(_("is full"), default=False)
    
    class Meta:
        verbose_name = _("Event Workshop")
        verbose_name_plural = _("Event Workshops")
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.title} - {self.event.name}"
    
    @property
    def current_participant_count(self):
        # This would typically be implemented with a through model for workshop participants
        return 0  # Placeholder - you'd implement actual counting logic

class EventDayAttendance (models.Model):
    '''
    Represents attendance records for events - supports multiple check-ins per day
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="attendance_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_attendance")
    
    check_in_time = models.DateTimeField(_("check-in timestamp"))
    check_out_time = models.DateTimeField(_("check-out timestamp"), blank=True, null=True)
    
    stale = models.BooleanField(editable=False, default=False, help_text=_("marks this attendance object as stale and can no longer be updated"))
    
    class Meta:
        verbose_name = _("Event Day Attendance")
        verbose_name_plural = _("Event Day Attendances")
        ordering = ['-check_in_time']
        indexes = [
            models.Index(fields=['event', 'user', 'check_in_time']),
            models.Index(fields=['event', 'check_in_time']),
        ]
    
    def __str__(self):
        return f"Attendance: {self.user} - {self.event.name} - {self.check_in_time}"
    
    @property
    def day_index(self):
        """
        Calculate 1-based day index from event start date.
        Day 1 = event start date, Day 2 = start + 1 day, etc.
        """
        if not self.check_in_time or not self.event.start_date:
            return None
        
        # Extract date from check_in_time (should be datetime)
        from datetime import datetime, date, time
        if isinstance(self.check_in_time, datetime):
            check_in_date = self.check_in_time.date()
        elif isinstance(self.check_in_time, date):
            check_in_date = self.check_in_time
        elif isinstance(self.check_in_time, time):
            # Old data format - time only, assume today's date for calculation
            return 1
        else:
            return None
        
        # Extract date from event start_date
        if isinstance(self.event.start_date, datetime):
            event_start = self.event.start_date.date()
        elif isinstance(self.event.start_date, date):
            event_start = self.event.start_date
        else:
            return None
        
        delta = (check_in_date - event_start).days
        return max(1, delta + 1)
    
    @property
    def day_date(self):
        """The date of this attendance record"""
        if not self.check_in_time:
            return None
        
        from datetime import datetime, date, time
        if isinstance(self.check_in_time, datetime):
            return self.check_in_time.date()
        elif isinstance(self.check_in_time, date):
            return self.check_in_time
        elif isinstance(self.check_in_time, time):
            # Old data format - time only, return today's date
            from datetime import date as date_today
            return date_today.today()
        return None

    @property
    def duration(self):
        from datetime import datetime, date
        """Calculate duration if both check-in and check-out exist"""
        if self.check_in_time and self.check_out_time:
            return self.check_out_time - self.check_in_time
        return None
    
    @property
    def is_finished(self):
        '''
        this attendance object is declared as "finished" if the user has checked out
        '''
        return self.check_in_time is not None and self.check_out_time is not None
    
    def clean(self):
        """Validate attendance record"""
        super().clean()
        
        if self.check_in_time and self.event.start_date and self.event.end_date:
            check_in_date = self.check_in_time.date() if hasattr(self.check_in_time, 'date') else self.check_in_time
            event_start = self.event.start_date.date() if hasattr(self.event.start_date, 'date') else self.event.start_date
            event_end = self.event.end_date.date() if hasattr(self.event.end_date, 'date') else self.event.end_date
            
            if check_in_date < event_start:
                raise ValidationError(_("Check-in date cannot be before event start date"))
            if check_in_date > event_end:
                raise ValidationError(_("Check-in date cannot be after event end date"))
        
        if self.check_out_time and self.check_in_time:
            if self.check_out_time <= self.check_in_time:
                raise ValidationError(_("Check-out must be after check-in"))
    
    def save(self, *args, **kwargs):
        # Run validation
        self.full_clean()
        
        # Mark as stale if finished
        if self.is_finished:
            self.stale = True
                
        return super().save(*args, **kwargs)