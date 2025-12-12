"""
Email utilities for sending shop/order-related emails.
Handles order confirmations, payment receipts, and order status updates.
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags


def send_order_confirmation_email(cart, payment):
    """
    Send an order confirmation email with product details, payment information, and order summary.
    
    Args:
        cart (EventCart): The cart/order instance
        payment (ProductPayment): The payment instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        user = cart.user
        
        # Get user email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for user {user.member_id}")
            return False
        
        # Get all orders with product details
        orders = cart.orders.select_related('product', 'size').prefetch_related('product__images').all()
        
        # Calculate order totals
        subtotal = 0
        order_items = []
        
        for order in orders:
            product = order.product
            unit_price = order.price_at_purchase or product.price
            discount = order.discount_applied or 0
            line_total = (unit_price - discount) * order.quantity
            subtotal += line_total
            
            # Get product image URL
            product_image_url = None
            if product.images.exists():
                first_image = product.images.first()
                if first_image and first_image.image:
                    # Get absolute URL for email
                    product_image_url = first_image.image.url
                    if not product_image_url.startswith('http'):
                        # Make it absolute if it's relative
                        base_url = settings.MEDIA_URL
                        if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN'):
                            product_image_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{first_image.image.name}"
                        else:
                            product_image_url = f"{base_url}{first_image.image.name}"
            
            order_items.append({
                'product': product,
                'order': order,
                'unit_price': unit_price,
                'discount': discount,
                'line_total': line_total,
                'size': order.size.size if order.size else None,
                'image_url': product_image_url,
            })
        
        shipping_cost = float(cart.shipping_cost) if cart.shipping_cost else 0
        total = subtotal + shipping_cost
        
        # Get payment method details and instructions
        payment_method_name = payment.method.get_method_display() if payment.method else "N/A"
        payment_instructions = None
        is_bank_transfer = False
        
        if payment.method:
            if payment.method.method == 'BANK_TRANSFER':
                is_bank_transfer = True
                payment_instructions = payment.get_bank_transfer_instructions()
                # Add dashboard instruction for bank transfer
                if payment_instructions:
                    payment_instructions += "\n\n💡 Visit your event dashboard to view complete bank transfer details and account information."
            elif payment.method.instructions:
                payment_instructions = payment.method.instructions
        
        # Prepare context for email template
        context = {
            'user': user,
            'cart': cart,
            'payment': payment,
            'order_items': order_items,
            'subtotal': subtotal,
            'shipping_cost': shipping_cost,
            'total': total,
            'order_reference': cart.order_reference_id,
            'payment_reference': payment.payment_reference_id,
            'bank_reference': payment.bank_reference,
            'payment_method': payment_method_name,
            'payment_status': payment.get_status_display(),
            'payment_verified': payment.approved,
            'payment_instructions': payment_instructions,
            'is_bank_transfer': is_bank_transfer,
            'event': cart.event,
            'event_name': cart.event.name if cart.event else "Event",
            'shipping_address': cart.shipping_address,
        }
        
        # Render email templates
        subject = f'Order Confirmation - {cart.order_reference_id}'
        html_message = render_to_string('emails/order_confirmation.html', context)
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
        
        print(f"✅ Order confirmation email sent to {recipient_email} for order {cart.order_reference_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order confirmation email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_payment_verified_email(cart, payment):
    """
    Send a payment verification notification email for order.
    
    Args:
        cart (EventCart): The cart/order instance
        payment (ProductPayment): The payment instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        user = cart.user
        
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for user {user.member_id}")
            return False
        
        # Get all orders with product details (same as order confirmation)
        orders = cart.orders.select_related('product', 'size').prefetch_related('product__images').all()
        
        # Calculate order totals
        subtotal = 0
        order_items = []
        
        for order in orders:
            product = order.product
            unit_price = float(order.price_at_purchase) if order.price_at_purchase else 0
            quantity = order.quantity
            line_total = unit_price * quantity
            subtotal += line_total
            
            # Get product image URL
            product_image_url = None
            if product.images.exists():
                first_image = product.images.first()
                if first_image and first_image.image:
                    image_url = first_image.image.url
                    # Convert relative URL to absolute for email
                    if image_url.startswith('/'):
                        image_url = f"{settings.MEDIA_URL.rstrip('/')}{image_url}"
                    # Handle S3 URLs
                    if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN') and settings.AWS_S3_CUSTOM_DOMAIN:
                        if not image_url.startswith('http'):
                            image_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}{image_url}"
                    product_image_url = image_url
            
            order_items.append({
                'product_name': product.title,
                'size': order.size.size if order.size else None,
                'quantity': quantity,
                'unit_price': unit_price,
                'line_total': line_total,
                'image_url': product_image_url,
            })
        
        shipping_cost = float(cart.shipping_cost) if cart.shipping_cost else 0
        total = subtotal + shipping_cost
        
        context = {
            'user': user,
            'cart': cart,
            'payment': payment,
            'order_reference': cart.order_reference_id,
            'payment_reference': payment.payment_reference_id,
            'payment_amount': payment.amount,
            'event_name': cart.event.name if cart.event else "Event",
            'order_items': order_items,
            'subtotal': subtotal,
            'shipping_cost': shipping_cost,
            'total': total,
        }
        
        subject = f'Payment Verified - Order {cart.order_reference_id}'
        html_message = render_to_string('emails/order_payment_verified.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        print(f"✅ Payment verification email sent to {recipient_email} for order {cart.order_reference_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send payment verification email: {e}")
        return False


def send_order_update_email(cart, order, updated_fields):
    """
    Send an email notification when an admin updates a user's order.
    
    Args:
        cart (EventCart): The cart/order instance
        order (EventProductOrder): The specific order that was updated
        updated_fields (dict): Dictionary of fields that were changed with their new values
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        user = cart.user
        
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for user {user.member_id}")
            return False
        
        # Get product image URL
        product_image_url = None
        if order.product.images.exists():
            first_image = order.product.images.first()
            if first_image and first_image.image:
                image_url = first_image.image.url
                if image_url.startswith('/'):
                    image_url = f"{settings.MEDIA_URL.rstrip('/')}{image_url}"
                if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN') and settings.AWS_S3_CUSTOM_DOMAIN:
                    if not image_url.startswith('http'):
                        image_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}{image_url}"
                product_image_url = image_url
        
        context = {
            'user': user,
            'cart': cart,
            'order': order,
            'product': order.product,
            'order_reference': cart.order_reference_id,
            'event_name': cart.event.name if cart.event else "Event",
            'updated_fields': updated_fields,
            'product_image_url': product_image_url,
            'size': order.size.size if order.size else None,
        }
        
        subject = f'Order Updated - {cart.order_reference_id}'
        html_message = render_to_string('emails/order_updated.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        print(f"✅ Order update email sent to {recipient_email} for order {cart.order_reference_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order update email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_cart_created_by_admin_email(cart):
    """
    Send an email notification when an admin/organizer creates a cart on behalf of a user.
    
    Args:
        cart (EventCart): The cart instance created by admin
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        user = cart.user
        
        # Get user email
        recipient_email = user.primary_email
        if not recipient_email:
            print(f"⚠️ No email address for user {user.member_id}")
            return False
        
        # Get all orders with product details
        orders = cart.orders.select_related('product', 'size').prefetch_related('product__images').all()
        
        # Calculate order totals
        subtotal = 0
        order_items = []
        
        for order in orders:
            product = order.product
            unit_price = order.price_at_purchase or product.price
            line_total = unit_price * order.quantity
            subtotal += line_total
            
            # Get product image URL - AWS S3 compatible
            product_image_url = None
            if product.images.exists():
                first_image = product.images.first()
                if first_image and first_image.image:
                    # Get absolute URL for email
                    product_image_url = first_image.image.url
                    if not product_image_url.startswith('http'):
                        # Make it absolute if it's relative
                        if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN'):
                            # AWS S3 URL
                            product_image_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{first_image.image.name}"
                        else:
                            # Local development URL
                            base_url = settings.MEDIA_URL
                            product_image_url = f"{base_url}{first_image.image.name}"
            
            order_items.append({
                'product_name': product.title,
                'quantity': order.quantity,
                'price_at_purchase': unit_price,
                'total_price': line_total,
                'size': order.size.size if order.size else None,
                'image_url': product_image_url,
            })
        
        shipping_cost = float(cart.shipping_cost) if cart.shipping_cost else 0
        total = subtotal + shipping_cost
        
        # Prepare context for email template
        context = {
            'user': user,
            'cart': cart,
            'order_items': order_items,
            'subtotal': subtotal,
            'shipping_cost': shipping_cost,
            'total': total,
            'order_reference': cart.order_reference_id,
            'event_name': cart.event.name if cart.event else "Event",
            'shipping_address': cart.shipping_address,
            'notes': cart.notes,
            'created_date': cart.created.strftime('%B %d, %Y at %I:%M %p') if cart.created else "Recently",
        }
        
        # Render email templates
        subject = f'Cart Created for You - {cart.event.name if cart.event else "Event"}'
        html_message = render_to_string('emails/cart_created_by_admin.html', context)
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
        
        print(f"✅ Admin cart creation email sent to {recipient_email} for cart {cart.order_reference_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send admin cart creation email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_order_refund_created_email(refund):
    """
    Send email notification when an order refund is created.
    
    Args:
        refund (OrderRefund): The refund instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get customer email
        recipient_email = refund.customer_email or (refund.user.primary_email if refund.user else None)
        if not recipient_email:
            print(f"⚠️ No email address for refund {refund.refund_reference}")
            return False
        
        # Extract cart order items
        order_items = []
        if refund.cart:
            orders = refund.cart.orders.select_related('product', 'size').all()
            for order in orders:
                product = order.product
                order_items.append({
                    'product_name': product.title if product else 'Unknown',
                    'quantity': order.quantity,
                    'size': order.size.size if order.size else None,
                    'price': float(order.price_at_purchase) if order.price_at_purchase else 0,
                })
        
        # Prepare context with extracted data
        context = {
            'customer_name': refund.customer_name,
            'refund_amount': float(refund.refund_amount),
            'refund_reference': refund.refund_reference,
            'is_automatic': refund.is_automatic_refund,
            'refund_reason': refund.get_refund_reason_display(),
            'reason_details': refund.reason_details,
            'refund_contact_email': refund.refund_contact_email,
            'order_reference': refund.cart.order_reference_id if refund.cart else 'N/A',
            'event_name': refund.event.name if refund.event else 'Event',
            'order_items': order_items,
            'created_at': refund.created_at,
        }
        
        # Render email templates
        subject = f"Refund Request Created - {refund.refund_reference}"
        html_message = render_to_string('emails/order_refund_created.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        print(f"📧 Order refund created email sent to {recipient_email} for {refund.refund_reference}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order refund created email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_order_refund_processed_email(refund):
    """
    Send email notification when an order refund is processed/completed.
    
    Args:
        refund (OrderRefund): The refund instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get customer email
        recipient_email = refund.customer_email or (refund.user.primary_email if refund.user else None)
        if not recipient_email:
            print(f"⚠️ No email address for refund {refund.refund_reference}")
            return False
        
        # Extract cart order items
        order_items = []
        if refund.cart:
            orders = refund.cart.orders.select_related('product', 'size').all()
            for order in orders:
                product = order.product
                order_items.append({
                    'product_name': product.title if product else 'Unknown',
                    'quantity': order.quantity,
                    'size': order.size.size if order.size else None,
                    'price': float(order.price_at_purchase) if order.price_at_purchase else 0,
                })
        
        # Prepare context with extracted data
        context = {
            'customer_name': refund.customer_name,
            'refund_amount': float(refund.refund_amount),
            'refund_reference': refund.refund_reference,
            'is_automatic': refund.is_automatic_refund,
            'refund_method': refund.refund_method or ('Stripe' if refund.is_automatic_refund else 'Manual'),
            'processed_at': refund.processed_at,
            'processing_notes': refund.processing_notes,
            'refund_contact_email': refund.refund_contact_email or settings.DEFAULT_FROM_EMAIL,
            'order_reference': refund.cart.order_reference_id if refund.cart else 'N/A',
            'event_name': refund.event.name if refund.event else 'Event',
            'order_items': order_items,
        }
        
        # Render email templates
        subject = f"Refund Processed - {refund.refund_reference}"
        html_message = render_to_string('emails/order_refund_processed.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        print(f"📧 Order refund processed email sent to {recipient_email} for {refund.refund_reference}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order refund processed email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False


def send_order_refund_failed_email(refund):
    """
    Send email notification when an order refund fails.
    
    Args:
        refund (OrderRefund): The refund instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get customer email
        recipient_email = refund.customer_email or (refund.user.primary_email if refund.user else None)
        if not recipient_email:
            print(f"⚠️ No email address for refund {refund.refund_reference}")
            return False
        
        # Extract cart order items
        order_items = []
        if refund.cart:
            orders = refund.cart.orders.select_related('product', 'size').all()
            for order in orders:
                product = order.product
                order_items.append({
                    'product_name': product.title if product else 'Unknown',
                    'quantity': order.quantity,
                    'size': order.size.size if order.size else None,
                    'price': float(order.price_at_purchase) if order.price_at_purchase else 0,
                })
        
        # Prepare context with extracted data
        context = {
            'customer_name': refund.customer_name,
            'refund_amount': float(refund.refund_amount),
            'refund_reference': refund.refund_reference,
            'failure_reason': refund.stripe_failure_reason or 'Unknown error',
            'refund_contact_email': refund.refund_contact_email or settings.DEFAULT_FROM_EMAIL,
            'order_reference': refund.cart.order_reference_id if refund.cart else 'N/A',
            'event_name': refund.event.name if refund.event else 'Event',
            'order_items': order_items,
        }
        
        # Render email templates
        subject = f"Refund Processing Failed - {refund.refund_reference}"
        html_message = render_to_string('emails/order_refund_failed.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        print(f"📧 Order refund failed email sent to {recipient_email} for {refund.refund_reference}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order refund failed email: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return False

