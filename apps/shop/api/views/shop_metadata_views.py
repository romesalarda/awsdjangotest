from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.shop.models.metadata_models import ProductCategory, ProductMaterial, ProductImage, ProductSize
from apps.shop.api.serializers.shop_metadata_serializers import (
    ProductCategorySerializer,
    ProductMaterialSerializer,
    ProductImageSerializer,
    ProductSizeSerializer,
)

class ProductCategoryViewSet(viewsets.ModelViewSet):
    '''
    Product categories for event products
    '''
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["title"]
    search_fields = ["title", "description"]
    ordering_fields = ["title"]
    ordering = ["title"]
    
    def get_permissions(self):
        """
        Allow authenticated users to read, only admin users to write
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

class ProductMaterialViewSet(viewsets.ModelViewSet):
    queryset = ProductMaterial.objects.all()
    serializer_class = ProductMaterialSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["title"]
    search_fields = ["title", "description"]
    ordering_fields = ["title"]
    ordering = ["title"]
    
    def get_permissions(self):
        """
        Allow authenticated users to read, only admin users to write
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.select_related("product").all()
    serializer_class = ProductImageSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["product", "product__title"]
    search_fields = ["product__title", "image"]
    ordering_fields = ["product__title", "uuid"]
    ordering = ["-uuid"]
    
class ProductSizeViewSet(viewsets.ModelViewSet):
    '''
    Endpoint for managing product sizes.
    '''
    queryset = ProductSize.objects.select_related("product").all()
    serializer_class = ProductSizeSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["product", "size"]
    search_fields = ["product__title", "size"]
    ordering_fields = ["product__title", "size", "price_modifier"]
    ordering = ["product__title", "size"]