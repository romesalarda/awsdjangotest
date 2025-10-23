"""
Email utilities for sending user-related emails.
Handles welcome emails and user account notifications.
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
import traceback


def send_welcome_email(user):
    """
    Send a welcome email to a newly registered user.
    
    Args:
        user (CommunityUser): The newly created user instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get user email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ User {user.username} has no primary email address")
            return False
        
        # Prepare context for email template
        context = {
            'user': user,
        }
        
        # Render email templates
        subject = 'Welcome to CEMS - Your Account is Ready!'
        html_message = render_to_string('emails/welcome.html', context)
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
        
        print(f"✅ Welcome email sent to {recipient_email} for user {user.username}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send welcome email: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False
