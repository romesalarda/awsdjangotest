"""
Celery Tasks for Event Lifecycle Management

This module contains asynchronous tasks for managing event lifecycles,
including automatic status transitions and cleanup operations.

Key Features:
- Timezone-aware datetime handling
- Idempotent operations (safe to run multiple times)
- Bulk updates for efficiency
- No data deletion
- Production-safe error handling

Tasks:
- mark_ended_events_as_completed: Automatically marks events as COMPLETED
  when their end_date has passed
"""

from celery import shared_task
from django.utils import timezone
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='events.mark_ended_events_as_completed',
    max_retries=3,
    default_retry_delay=60,  # Retry after 60 seconds
)
def mark_ended_events_as_completed(self):
    """
    Mark events as COMPLETED when their end_date has passed.
    
    This task:
    - Runs every 5 minutes (configured in django-celery-beat)
    - Only updates events in CONFIRMED or ONGOING status
    - Uses timezone-aware datetime comparison
    - Performs bulk updates (no per-row loops)
    - Is idempotent (safe to run multiple times)
    
    Events marked as COMPLETED:
    - Will not appear in public discovery/listing
    - Remain accessible via direct URL
    - Can still be accessed by event staff/supervisors
    
    Returns:
        int: Number of events marked as completed
    """
    try:
        # Import here to avoid circular imports
        from apps.events.models import Event
        
        # Get current time (timezone-aware)
        now = timezone.now()
        
        logger.info(f"[Event Lifecycle] Starting event lifecycle check at {now}")
        
        # Find events that have ended but are not yet marked as completed
        # Only consider events in CONFIRMED or ONGOING status
        events_to_complete = Event.objects.filter(
            end_date__lt=now,  # End date is in the past
            status__in=[
                Event.EventStatus.CONFIRMED,
                Event.EventStatus.ONGOING
            ]
        ).exclude(
            end_date__isnull=True  # Skip events without end_date
        )
        
        # Get count and IDs before update for logging
        event_count = events_to_complete.count()
        
        if event_count == 0:
            logger.info("[Event Lifecycle] No events to mark as completed")
            return 0
        
        # Get event details for logging
        event_ids = list(events_to_complete.values_list('id', flat=True))
        event_names = list(events_to_complete.values_list('name', flat=True)[:10])  # First 10 names
        
        logger.info(
            f"[Event Lifecycle] Found {event_count} events to mark as completed"
        )
        logger.info(
            f"[Event Lifecycle] Sample event names: {', '.join(event_names)}"
        )
        
        # Perform bulk update (efficient, single query)
        updated_count = events_to_complete.update(
            status=Event.EventStatus.COMPLETED
        )
        
        logger.info(
            f"[Event Lifecycle] Successfully marked {updated_count} events as COMPLETED"
        )
        logger.info(
            f"[Event Lifecycle] Event IDs updated: {event_ids}"
        )
        
        # Note: If you need to trigger WebSocket notifications or send emails
        # when events complete, you can iterate through the event_ids here
        # and call those functions. Example:
        # 
        # from apps.events.websocket_utils import notify_event_completed
        # for event_id in event_ids:
        #     notify_event_completed(event_id)
        
        return updated_count
        
    except Exception as exc:
        logger.error(
            f"[Event Lifecycle] Error marking events as completed: {str(exc)}",
            exc_info=True
        )
        # Retry the task if it fails (max 3 times)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.archive_old_completed_events',
    max_retries=3,
    default_retry_delay=60,
)
def archive_old_completed_events(self):
    """
    Archive events that have been completed for a specified duration.
    
    This is a placeholder task for future implementation.
    Use this to move old completed events to an archived state
    after a certain period (e.g., 90 days after completion).
    
    NOTE: This task is not currently scheduled. To enable it,
    create a periodic task in django-celery-beat admin interface.
    
    Returns:
        int: Number of events archived
    """
    logger.info("[Event Lifecycle] Archive task called (not yet implemented)")
    # Future implementation:
    # - Find events completed > 90 days ago
    # - Move to ARCHIVED status
    # - Update database records
    # - Send notifications if needed
    return 0


@shared_task(
    bind=True,
    name='events.send_event_reminder_emails',
    max_retries=3,
    default_retry_delay=60,
)
def send_event_reminder_emails(self):
    """
    Send reminder emails for upcoming events.
    
    This is a placeholder task for future implementation.
    Use this to send reminder emails to participants before events start.
    
    NOTE: This task is not currently scheduled. To enable it,
    create a periodic task in django-celery-beat admin interface.
    
    Returns:
        int: Number of emails sent
    """
    logger.info("[Event Lifecycle] Reminder email task called (not yet implemented)")
    # Future implementation:
    # - Find events starting in 24 hours
    # - Get all confirmed participants
    # - Send reminder emails
    # - Log sent emails
    return 0
