"""
Email utilities for sending event-related emails.
Handles booking confirmations, QR code generation, and participant notifications.
"""
import qrcode
import io
import traceback
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from datetime import datetime


def generate_qr_code(data):
    """
    Generate a QR code image from the given data.
    
    Args:
        data (str): The data to encode in the QR code (typically event_pax_id)
    
    Returns:
        io.BytesIO: QR code image as bytes
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO object
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return img_io


def send_booking_confirmation_email(participant):
    """
    Send a booking confirmation email to a participant with their QR code.
    
    Args:
        participant (EventParticipant): The participant instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        event = participant.event
        user = participant.user
        
        # Get participant email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for participant {participant.event_pax_id}")
            return False
        
        # Prepare context for email template
        context = {
            'participant': participant,
            'event': event,
            'user': user,
            'event_pax_id': participant.event_pax_id,
            'event_name': event.name,
            'event_start_date': event.start_date,
            'event_end_date': event.end_date,
            'event_venue': event.venues.filter(primary_venue=True).first() if event.venues.exists() else None,
            'status': participant.get_status_display(),
            'registration_date': participant.registration_date,
        }
        
        # Get payment information
        event_payment = participant.participant_event_payments.first()
        if event_payment:
            context['payment_package'] = event_payment.package
            context['payment_amount'] = event_payment.amount
            context['payment_verified'] = event_payment.verified
            context['payment_method'] = event_payment.method
            context['payment_method_name'] = event_payment.method.method if event_payment.method else None
        
        # Render email templates
        subject = f'Booking Confirmation - {event.name}'
        html_message = render_to_string('emails/booking_confirmation.html', context)
        plain_message = strip_tags(html_message)
        
        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        
        # Generate and attach QR code as inline image
        qr_code_data = participant.event_pax_id  # Use confirmation number as QR code data
        qr_image = generate_qr_code(qr_code_data)
        
        # Attach QR code as inline image with proper Content-ID
        from email.mime.image import MIMEImage
        qr_mime = MIMEImage(qr_image.getvalue())
        qr_mime.add_header('Content-ID', f'<qr_code_{participant.event_pax_id}.png>')
        qr_mime.add_header('Content-Disposition', 'inline', filename=f'qr_code_{participant.event_pax_id}.png')
        email.attach(qr_mime)
        
        # Send email
        email.send(fail_silently=False)
        
        print(f"✅ Booking confirmation email sent to {recipient_email} for {participant.event_pax_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send booking confirmation email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_payment_verification_email(participant):
    """
    Send a payment verification notification email.
    
    Args:
        participant (EventParticipant): The participant instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        event = participant.event
        user = participant.user
        
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for participant {participant.event_pax_id}")
            return False
        
        # Get payment information
        event_payment = participant.participant_event_payments.first()
        payment_reference = event_payment.event_payment_tracking_number if event_payment else None
        payment_amount = event_payment.amount if event_payment else None
        
        context = {
            'participant': participant,
            'event': event,
            'user': user,
            'event_name': event.name,
            'payment_reference': payment_reference,
            'payment_amount': payment_amount,
        }
        
        subject = f'Payment Verified - {event.name}'
        html_message = render_to_string('emails/payment_verified.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        print(f"✅ Payment verification email sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send payment verification email: {e}")
        return False


def send_participant_question_email(participant_question):
    """
    Send email to event organizers when a participant submits a question.
    
    Args:
        participant_question (ParticipantQuestion): The participant question instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        participant = participant_question.participant
        event = participant.event
        user = participant.user
        
        # Get organizer emails
        organizer_emails = []
        
        # Add supervising youth heads
        if event.supervising_youth_heads.exists():
            for youth_head in event.supervising_youth_heads.all():
                if youth_head.primary_email:
                    organizer_emails.append(youth_head.primary_email)
        
        # Add supervising CFC coordinators
        if event.supervising_CFC_coordinators.exists():
            for coordinator in event.supervising_CFC_coordinators.all():
                if coordinator.primary_email:
                    organizer_emails.append(coordinator.primary_email)
        
        # Remove duplicates
        organizer_emails = list(set(organizer_emails))
        
        if not organizer_emails:
            print(f"⚠️ No organizer emails found for event {event.name}")
            return False
        
        # Map priority to CSS class
        priority_class_map = {
            'high': 'high',
            'medium': 'medium',
            'low': 'low'
        }
        
        # Prepare context for email template
        context = {
            'event_name': event.name,
            'participant_name': user.get_full_name() or user.username,
            'participant_email': user.primary_email,
            'event_pax_id': participant.event_pax_id,
            'question_subject': participant_question.question_subject,
            'question_body': participant_question.question,
            'question_type': participant_question.questions_type,
            'priority': participant_question.priority,
            'priority_class': priority_class_map.get(participant_question.priority, 'low'),
            'submitted_at': participant_question.submitted_at.strftime('%B %d, %Y at %I:%M %p'),
            'year': datetime.now().year,
        }
        
        # Render email templates
        subject = f'New Question from {user.get_full_name() or user.username} - {event.name}'
        html_message = render_to_string('emails/participant_question_submitted.html', context)
        plain_message = strip_tags(html_message)
        
        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=organizer_emails
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        print(f"✅ Question notification email sent to {len(organizer_emails)} organizers for question #{participant_question.id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send participant question email: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_question_answer_email(participant_question):
    """
    Send email to participant when an organizer answers their question.
    
    Args:
        participant_question (ParticipantQuestion): The participant question instance with answer
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        participant = participant_question.participant
        event = participant.event
        user = participant.user
        
        # Get participant email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for participant {participant.event_pax_id}")
            return False
        
        # Get answered by user's name
        answered_by_name = "Event Organizer"
        if participant_question.answered_by:
            answered_by_name = participant_question.answered_by.get_full_name() or participant_question.answered_by.username
        
        # Prepare context for email template
        context = {
            'event_name': event.name,
            'participant_name': user.get_full_name() or user.username,
            'question_subject': participant_question.question_subject,
            'question_body': participant_question.question,
            'answer': participant_question.answer,
            'answered_by': answered_by_name,
            'responded_at': participant_question.responded_at.strftime('%B %d, %Y at %I:%M %p') if participant_question.responded_at else datetime.now().strftime('%B %d, %Y at %I:%M %p'),
            'year': datetime.now().year,
        }
        
        # Render email templates
        subject = f'Your Question Has Been Answered - {event.name}'
        html_message = render_to_string('emails/participant_question_answered.html', context)
        plain_message = strip_tags(html_message)
        
        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        print(f"✅ Question answer email sent to {recipient_email} for question #{participant_question.id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send question answer email: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_participant_removal_email(participant, reason, payment_details):
    """
    Send email to participant when they are removed from an event.
    
    Args:
        participant (EventParticipant): The participant instance being removed
        reason (str): Reason for removal provided by event organizer
        payment_details (dict): Dictionary containing payment information:
            - has_payments (bool): Whether participant has made any payments
            - event_payment_total (Decimal): Total amount paid for event registration
            - product_payment_total (Decimal): Total amount paid for merchandise
            - total_amount (Decimal): Total amount paid overall
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        event = participant.event
        user = participant.user
        
        # Get participant email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for participant {participant.event_pax_id}")
            print(f"   Participant will be removed without email notification")
            return False
        
        # Get event organizer email (will be used as contact for refunds)
        organizer_emails = []
        if event.supervising_youth_heads.exists():
            for youth_head in event.supervising_youth_heads.all():
                if youth_head.primary_email:
                    organizer_emails.append(youth_head.primary_email)
        
        if event.supervising_CFC_coordinators.exists():
            for coordinator in event.supervising_CFC_coordinators.all():
                if coordinator.primary_email:
                    organizer_emails.append(coordinator.primary_email)
        
        # Use first organizer email or fallback
        organizer_contact_email = organizer_emails[0] if organizer_emails else settings.DEFAULT_FROM_EMAIL
        
        # Prepare context for email template
        context = {
            'participant_name': user.get_full_name() or user.username,
            'event_name': event.name,
            'event_start_date': event.start_date,
            'event_end_date': event.end_date,
            'reason': reason,
            'has_payments': payment_details.get('has_payments', False),
            'event_payment_total': payment_details.get('event_payment_total', 0),
            'product_payment_total': payment_details.get('product_payment_total', 0),
            'total_amount': payment_details.get('total_amount', 0),
            'organizer_email': organizer_contact_email,
            'year': datetime.now().year,
        }
        
        # Render email templates
        subject = f'Registration Removed - {event.name}'
        html_message = render_to_string('emails/participant_removal.html', context)
        plain_message = strip_tags(html_message)
        
        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        print(f"✅ Participant removal email sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send participant removal email: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False

