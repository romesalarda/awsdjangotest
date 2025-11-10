"""
Management command to expire locked carts and release inventory.
Run this periodically (e.g., every 5 minutes) via cron or Celery beat.

Usage:
    python manage.py expire_locked_carts
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.shop.models.shop_models import EventCart
from apps.shop.models.payments import ProductPaymentLog, ProductPayment


class Command(BaseCommand):
    help = 'Expire locked carts that have exceeded their lock timeout'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be expired without actually expiring',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find locked carts that have expired
        now = timezone.now()
        expired_carts = EventCart.objects.filter(
            cart_status=EventCart.CartStatus.LOCKED,
            lock_expires_at__lt=now
        ).select_related('user')
        
        count = expired_carts.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would expire {count} locked carts')
            )
            for cart in expired_carts:
                self.stdout.write(f'  - Cart {cart.order_reference_id} (user: {cart.user.email})')
            return
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No expired carts found'))
            return
        
        # Expire the carts
        expired_count = 0
        for cart in expired_carts:
            try:
                with transaction.atomic():
                    # Update cart status
                    cart.cart_status = EventCart.CartStatus.EXPIRED
                    cart.active = False
                    cart.submitted = False
                    cart.save()
                    
                    # Update any pending payments
                    pending_payments = ProductPayment.objects.filter(
                        cart=cart,
                        status=ProductPayment.PaymentStatus.PENDING
                    )
                    
                    for payment in pending_payments:
                        payment.status = ProductPayment.PaymentStatus.FAILED
                        payment.save()
                        
                        # Log the expiration
                        ProductPaymentLog.log_action(
                            payment=payment,
                            action='cart_expired',
                            old_status=ProductPayment.PaymentStatus.PENDING,
                            new_status=ProductPayment.PaymentStatus.FAILED,
                            notes=f'Cart lock expired after {cart.lock_expires_at}'
                        )
                    
                    expired_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Expired cart {cart.order_reference_id} (user: {cart.user.email})'
                        )
                    )
            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Failed to expire cart {cart.order_reference_id}: {str(e)}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully expired {expired_count}/{count} carts'
            )
        )
