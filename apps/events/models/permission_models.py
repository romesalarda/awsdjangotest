from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import uuid


class ServiceTeamPermission(models.Model):
    """
    Permission model for event service team members.
    Supports both role-based and granular action-based permissions.
    
    Permission Hierarchy:
    1. Event Creator - Full permissions (auto-granted)
    2. Event Heads - Full permissions (auto-granted)
    3. CFC Coordinators - Full permissions (auto-granted)
    4. Service Team Members - Customizable permissions
    """
    
    class PermissionRole(models.TextChoices):
        """
        Role-based permission templates that can be assigned.
        Each role comes with a default set of granular permissions.
        """
        ADMIN = "ADMIN", _("Admin - Full Access")
        MERCH_ONLY = "MERCH_ONLY", _("Merchandise Only")
        SCANNER_ONLY = "SCANNER_ONLY", _("Scanner Only")
        PARTICIPANT_MANAGEMENT = "PARTICIPANT_MANAGEMENT", _("Participant Management")
        CUSTOM = "CUSTOM", _("Custom Permissions")
    
    id = models.UUIDField(
        verbose_name=_("permission id"), 
        default=uuid.uuid4, 
        editable=False, 
        primary_key=True
    )
    
    service_team_member = models.OneToOneField(
        "EventServiceTeamMember",
        on_delete=models.CASCADE,
        related_name="permissions",
        verbose_name=_("service team member")
    )
    
    # Role-based permission (template)
    role = models.CharField(
        _("permission role"),
        max_length=30,
        choices=PermissionRole.choices,
        default=PermissionRole.CUSTOM,
        help_text=_("Role-based permission template. CUSTOM allows granular control.")
    )
    
    # Granular Permissions - Participant Management
    can_view_participants = models.BooleanField(
        _("can view participants"),
        default=False,
        help_text=_("Can view participant list and details")
    )
    
    can_edit_participants = models.BooleanField(
        _("can edit participants"),
        default=False,
        help_text=_("Can edit participant details, registration info")
    )
    
    can_remove_participants = models.BooleanField(
        _("can remove participants"),
        default=False,
        help_text=_("Can remove participants from event")
    )
    
    can_add_participants = models.BooleanField(
        _("can add participants"),
        default=False,
        help_text=_("Can add new participants to event")
    )
    
    # Granular Permissions - Payment Management
    can_view_payments = models.BooleanField(
        _("can view participant payments"),
        default=False,
        help_text=_("Can view participant payment records")
    )
    
    can_view_event_payment_statistics = models.BooleanField(
        _("can view payment statistics"),
        default=False,
        help_text=_("Can view overall payment statistics and reports")
    )
    
    can_approve_payments = models.BooleanField(
        _("can approve payments"),
        default=False,
        help_text=_("Can verify and approve event payments")
    )
    
    can_process_refunds = models.BooleanField(
        _("can process refunds"),
        default=False,
        help_text=_("Can process participant refunds")
    )
    
    # Granular Permissions - Merchandise Management
    can_view_merch = models.BooleanField(
        _("can view merchandise"),
        default=False,
        help_text=_("Can view merchandise and orders")
    )
    
    can_manage_merch = models.BooleanField(
        _("can manage merchandise"),
        default=False,
        help_text=_("Can create, edit, delete merchandise and manage orders")
    )
    
    can_approve_merch_payments = models.BooleanField(
        _("can approve merch payments"),
        default=False,
        help_text=_("Can verify merchandise payments")
    )
    
    # Granular Permissions - Check-in & Live Dashboard
    can_access_checkin = models.BooleanField(
        _("can access check-in"),
        default=False,
        help_text=_("Can access event check-in scanner and dashboard")
    )
    
    can_access_live_dashboard = models.BooleanField(
        _("can access live dashboard"),
        default=False,
        help_text=_("Can access real-time event dashboard and analytics")
    )
    
    # Granular Permissions - Event Management
    can_edit_event_details = models.BooleanField(
        _("can edit event details"),
        default=False,
        help_text=_("Can edit event basic information, venue, dates")
    )
    
    can_manage_service_team = models.BooleanField(
        _("can manage service team"),
        default=False,
        help_text=_("Can add/remove service team members")
    )
    
    can_manage_permissions = models.BooleanField(
        _("can manage permissions"),
        default=False,
        help_text=_("Can set permissions for other service team members")
    )
    
    can_delete_event = models.BooleanField(
        _("can delete event"),
        default=False,  
        help_text=_("Can delete the event entirely")
    )
    
    can_view_management_dashboard = models.BooleanField(
        _("can view management dashboard"),
        default=False,
        help_text=_("Can access the event management dashboard")
    )
    
    can_publish_event = models.BooleanField(
        _("can publish event"),
        default=False,
        help_text=_("Can publish the event to make it live")    
    )

    # Granular Permissions - Resources & Q&A
    can_manage_resources = models.BooleanField(
        _("can manage resources"),
        default=False,
        help_text=_("Can add/edit/delete event resources")
    )
    
    can_manage_questions = models.BooleanField(
        _("can manage questions"),
        default=False,
        help_text=_("Can view and respond to participant questions")
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_permissions",
        verbose_name=_("granted by")
    )
    
    class Meta:
        verbose_name = _("Service Team Permission")
        verbose_name_plural = _("Service Team Permissions")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.service_team_member.user} - {self.get_role_display()}"
    
    def apply_role_template(self):
        """
        Apply permission template based on the selected role.
        This sets all granular permissions according to the role.
        """
        if self.role == self.PermissionRole.ADMIN:
            # Full access to everything
            self.can_view_participants = True
            self.can_edit_participants = True
            self.can_remove_participants = True
            self.can_add_participants = True
            self.can_view_payments = True
            self.can_approve_payments = True
            self.can_process_refunds = True
            self.can_view_merch = True
            self.can_manage_merch = True
            self.can_approve_merch_payments = True
            self.can_access_checkin = True
            self.can_access_live_dashboard = True
            self.can_edit_event_details = True
            self.can_manage_service_team = True
            self.can_manage_permissions = True
            self.can_manage_resources = True
            self.can_manage_questions = True
            
            self.can_view_event_payment_statistics = True
            self.can_publish_event = True
            self.can_view_management_dashboard = True
            self.can_delete_event = True
            
        elif self.role == self.PermissionRole.MERCH_ONLY:
            # Merchandise management only
            self.can_view_participants = False
            self.can_edit_participants = False
            self.can_remove_participants = False
            self.can_add_participants = False
            self.can_view_payments = False
            self.can_approve_payments = False
            self.can_process_refunds = False
            self.can_view_merch = True
            self.can_manage_merch = True
            self.can_approve_merch_payments = True
            self.can_access_checkin = False
            self.can_access_live_dashboard = False
            self.can_edit_event_details = False
            self.can_manage_service_team = False
            self.can_manage_permissions = False
            self.can_manage_resources = False
            self.can_manage_questions = False
            
            self.can_view_payments_statistics = False
            self.can_publish_event = False
            self.can_view_management_dashboard = True
            self.can_delete_event = False
            
        elif self.role == self.PermissionRole.SCANNER_ONLY:
            # Check-in and live dashboard only
            self.can_view_participants = True  # Need to see participants for check-in
            self.can_edit_participants = False
            self.can_remove_participants = False
            self.can_add_participants = False
            self.can_view_payments = False
            self.can_approve_payments = False
            self.can_process_refunds = False
            self.can_view_merch = False
            self.can_manage_merch = False
            self.can_approve_merch_payments = False
            self.can_access_checkin = True
            self.can_access_live_dashboard = True
            self.can_edit_event_details = False
            self.can_manage_service_team = False
            self.can_manage_permissions = False
            self.can_manage_resources = False
            self.can_manage_questions = False
            
            self.can_view_payments_statistics = False
            self.can_publish_event = False
            self.can_view_management_dashboard = True
            self.can_delete_event = False
            
        elif self.role == self.PermissionRole.PARTICIPANT_MANAGEMENT:
            # Participant management with configurable payment approval
            self.can_view_participants = True
            self.can_edit_participants = True
            self.can_remove_participants = False  # Generally restricted
            self.can_add_participants = True
            self.can_view_payments = True
            self.can_approve_payments = False  # Can be enabled separately
            self.can_process_refunds = False  # Generally restricted
            self.can_view_merch = False
            self.can_manage_merch = False
            self.can_approve_merch_payments = False
            self.can_access_checkin = False
            self.can_access_live_dashboard = False
            self.can_edit_event_details = False
            self.can_manage_service_team = False
            self.can_manage_permissions = False
            self.can_manage_resources = False
            self.can_manage_questions = True  # Can handle participant questions
            
            self.can_view_payments_statistics = False
            self.can_publish_event = False
            self.can_view_management_dashboard = True
            self.can_delete_event = False
    
    def save(self, *args, **kwargs):
        """
        Auto-apply role template if role is not CUSTOM and this is a new record
        or role has changed.
        """
        if self.pk is None:  # New record
            if self.role != self.PermissionRole.CUSTOM:
                self.apply_role_template()
        else:  # Existing record
            try:
                old_instance = ServiceTeamPermission.objects.get(pk=self.pk)
                if old_instance.role != self.role and self.role != self.PermissionRole.CUSTOM:
                    self.apply_role_template()
            except ServiceTeamPermission.DoesNotExist:
                # Edge case: pk is set but object doesn't exist in DB yet
                if self.role != self.PermissionRole.CUSTOM:
                    self.apply_role_template()
        
        super().save(*args, **kwargs)
    
    def has_any_permission(self):
        """Check if user has any permission at all."""
        return any([
            self.can_view_participants,
            self.can_edit_participants,
            self.can_remove_participants,
            self.can_add_participants,
            self.can_view_payments,
            self.can_approve_payments,
            self.can_process_refunds,
            self.can_view_merch,
            self.can_manage_merch,
            self.can_approve_merch_payments,
            self.can_access_checkin,
            self.can_access_live_dashboard,
            self.can_edit_event_details,
            self.can_manage_service_team,
            self.can_manage_permissions,
            self.can_manage_resources,
            self.can_manage_questions,
            self.can_view_event_payment_statistics, 
            self.can_publish_event,
            self.can_view_management_dashboard,
            self.can_delete_events
        ])
