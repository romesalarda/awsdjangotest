"""
Celery tasks for event email sending.
All email operations are offloaded to background workers.
"""
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='events.send_booking_confirmation_email',
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def send_booking_confirmation_email_task(self, participant_id):
    """
    Send booking confirmation email with QR code.
    
    Args:
        participant_id: EventParticipant UUID
    """
    try:
        from apps.events.models import EventParticipant
        from apps.events.email_utils import send_booking_confirmation_email
        
        participant = EventParticipant.objects.get(id=participant_id)
        result = send_booking_confirmation_email(participant)
        
        if result:
            logger.info(f"Booking confirmation email sent for participant {participant_id}")
        else:
            logger.warning(f"Failed to send booking confirmation for participant {participant_id}")
            
        return result
        
    except EventParticipant.DoesNotExist:
        logger.error(f"Participant {participant_id} not found")
        return False
    except Exception as exc:
        logger.error(f"Error sending booking confirmation: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.send_payment_verification_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_payment_verification_email_task(self, participant_id):
    """Send payment verification email."""
    try:
        from apps.events.models import EventParticipant
        from apps.events.email_utils import send_payment_verification_email
        
        participant = EventParticipant.objects.get(id=participant_id)
        result = send_payment_verification_email(participant)
        
        if result:
            logger.info(f"Payment verification email sent for participant {participant_id}")
        else:
            logger.warning(f"Failed to send payment verification for participant {participant_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending payment verification: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.send_participant_question_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_participant_question_email_task(self, question_id):
    """Send email to organizers when participant submits question."""
    try:
        from apps.events.models import ParticipantQuestion
        from apps.events.email_utils import send_participant_question_email
        
        question = ParticipantQuestion.objects.get(id=question_id)
        result = send_participant_question_email(question)
        
        if result:
            logger.info(f"Question notification email sent for question {question_id}")
        else:
            logger.warning(f"Failed to send question notification for question {question_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending question notification: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.send_question_answer_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_question_answer_email_task(self, question_id):
    """Send email to participant when their question is answered."""
    try:
        from apps.events.models import ParticipantQuestion
        from apps.events.email_utils import send_question_answer_email
        
        question = ParticipantQuestion.objects.get(id=question_id)
        result = send_question_answer_email(question)
        
        if result:
            logger.info(f"Answer email sent for question {question_id}")
        else:
            logger.warning(f"Failed to send answer email for question {question_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending answer email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.send_participant_removal_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_participant_removal_email_task(self, participant_id, reason, payment_details):
    """Send email when participant is removed from event."""
    try:
        from apps.events.models import EventParticipant
        from apps.events.email_utils import send_participant_removal_email
        
        participant = EventParticipant.objects.get(id=participant_id)
        result = send_participant_removal_email(participant, reason, payment_details)
        
        if result:
            logger.info(f"Removal email sent for participant {participant_id}")
        else:
            logger.warning(f"Failed to send removal email for participant {participant_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending removal email: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='events.send_refund_processed_email',
    max_retries=3,
    default_retry_delay=300,
)
def send_refund_processed_email_task(self, refund_id):
    """Send email when refund is processed."""
    try:
        from apps.events.models import ParticipantRefund
        from apps.events.email_utils import send_refund_processed_email
        
        refund = ParticipantRefund.objects.get(id=refund_id)
        result = send_refund_processed_email(refund)
        
        if result:
            logger.info(f"Refund processed email sent for refund {refund_id}")
        else:
            logger.warning(f"Failed to send refund processed email for refund {refund_id}")
            
        return result
        
    except Exception as exc:
        logger.error(f"Error sending refund processed email: {exc}")
        raise self.retry(exc=exc)
