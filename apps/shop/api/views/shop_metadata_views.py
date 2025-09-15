from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.shop.models.metadata_models import ProductCategory, ProductMaterial, ProductImage
from apps.shop.api.serializers.shop_metadata_serializers import (
    ProductCategorySerializer,
    ProductMaterialSerializer,
    ProductImageSerializer,
)

class ProductCategoryViewSet(viewsets.ModelViewSet):
    '''
    Product categories for event products
    '''
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["title"]
    search_fields = ["title", "description"]
    ordering_fields = ["title", "product_count"]
    ordering = ["title"]

class ProductMaterialViewSet(viewsets.ModelViewSet):
    queryset = ProductMaterial.objects.all()
    serializer_class = ProductMaterialSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["title"]
    search_fields = ["title", "description"]
    ordering_fields = ["title", "product_count"]
    ordering = ["title"]

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.select_related("product").all()
    serializer_class = ProductImageSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["product", "product__title"]
    search_fields = ["product__title", "image"]
    ordering_fields = ["product__title", "uuid"]
    ordering = ["-uuid"]