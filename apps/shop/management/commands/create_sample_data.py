from django.core.management.base import BaseCommand
from apps.shop.models.metadata_models import ProductCategory, ProductMaterial


class Command(BaseCommand):
    help = 'Create sample categories and materials for testing'

    def handle(self, *args, **options):
        # Create sample categories
        categories = [
            {'title': 'Clothing', 'description': 'Apparel and clothing items'},
            {'title': 'Accessories', 'description': 'Fashion accessories and add-ons'},
            {'title': 'Books', 'description': 'Books and publications'},
            {'title': 'Stationery', 'description': 'Writing and office supplies'},
            {'title': 'Tech', 'description': 'Technology and electronic items'},
            {'title': 'Souvenirs', 'description': 'Memorable keepsakes and gifts'},
        ]
        
        for cat_data in categories:
            category, created = ProductCategory.objects.get_or_create(
                title=cat_data['title'],
                defaults={'description': cat_data['description']}
            )
            if created:
                self.stdout.write(f'Created category: {category.title}')
            else:
                self.stdout.write(f'Category already exists: {category.title}')
        
        # Create sample materials
        materials = [
            {'title': 'Cotton', 'description': 'Natural cotton fiber'},
            {'title': 'Polyester', 'description': 'Synthetic polyester material'},
            {'title': 'Wool', 'description': 'Natural wool fiber'},
            {'title': 'Silk', 'description': 'Natural silk fiber'},
            {'title': 'Leather', 'description': 'Natural or synthetic leather'},
            {'title': 'Metal', 'description': 'Various metal materials'},
            {'title': 'Plastic', 'description': 'Synthetic plastic materials'},
            {'title': 'Paper', 'description': 'Paper-based materials'},
        ]
        
        for mat_data in materials:
            material, created = ProductMaterial.objects.get_or_create(
                title=mat_data['title'],
                defaults={'description': mat_data['description']}
            )
            if created:
                self.stdout.write(f'Created material: {material.title}')
            else:
                self.stdout.write(f'Material already exists: {material.title}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Sample data created! Categories: {ProductCategory.objects.count()}, '
                f'Materials: {ProductMaterial.objects.count()}'
            )
        )