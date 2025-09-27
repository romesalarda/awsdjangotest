from django.core.management.base import BaseCommand
from apps.shop.models.metadata_models import ProductSize
from apps.shop.models.shop_models import EventProduct
from collections import defaultdict

class Command(BaseCommand):
    help = 'Clean up duplicate ProductSize entries for each product'

    def handle(self, *args, **options):
        self.stdout.write("Starting cleanup of duplicate ProductSize entries...")
        
        products = EventProduct.objects.all()
        total_cleaned = 0
        
        for product in products:
            # Group sizes by product and size type
            size_groups = defaultdict(list)
            for size in product.product_sizes.all():
                size_groups[size.size].append(size)
            
            # Remove duplicates (keep the first one, delete the rest)
            product_cleaned = 0
            for size_value, size_list in size_groups.items():
                if len(size_list) > 1:
                    # Keep the first one, delete the rest
                    duplicates = size_list[1:]
                    for duplicate in duplicates:
                        duplicate.delete()
                        product_cleaned += 1
                        total_cleaned += 1
            
            if product_cleaned > 0:
                self.stdout.write(f"  Product '{product.title}': removed {product_cleaned} duplicate sizes")
        
        if total_cleaned > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Cleanup complete! Removed {total_cleaned} duplicate size entries.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("No duplicate sizes found. Database is clean!"))