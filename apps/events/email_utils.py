"""
Email utilities for sending event-related emails.
Handles booking confirmations, QR code generation, and participant notifications.
"""
import qrcode
import io
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags


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
        payment_reference = event_payment.payment_reference_id if event_payment else None
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
