from rest_framework.routers import DefaultRouter
from django.urls import path
from django.urls import include

from apps.shop.api.views.product_payment_views import (
    ProductPaymentMethodViewSet,
    ProductPaymentPackageViewSet,
    ProductPaymentViewSet,
)
from apps.shop.api.views.shop_metadata_views import (
    ProductCategoryViewSet, 
    ProductMaterialViewSet,
    ProductImageViewSet,
    ProductSizeViewSet,
)

from apps.shop.api.views.shop_views import ( 
    EventProductViewSet,
    EventCartViewSet,
    EventProductOrderViewSet,   
)

from apps.shop.api.views.order_refund_viewsets import OrderRefundViewSet
from apps.shop.api.views.stripe_views import stripe_webhook, create_payment_intent

production_payment_router = DefaultRouter()
production_payment_router.register(r'payment-methods', ProductPaymentMethodViewSet, basename='productpaymentmethod')
production_payment_router.register(r'payment-packages', ProductPaymentPackageViewSet, basename='productpaymentpackage')
production_payment_router.register(r'payments', ProductPaymentViewSet, basename='productpayment')

metadata = DefaultRouter()
metadata.register(r'categories', ProductCategoryViewSet, basename='productcategory')
metadata.register(r'materials', ProductMaterialViewSet, basename='productmaterial')
metadata.register(r'images', ProductImageViewSet, basename='productimage')
metadata.register(r'sizes', ProductSizeViewSet, basename='productsize')

shop = DefaultRouter()
shop.register(r'products', EventProductViewSet, basename='eventproduct')
shop.register(r'carts', EventCartViewSet, basename='eventcart')
shop.register(r'orders', EventProductOrderViewSet, basename='eventproductorder')
shop.register(r'order-refunds', OrderRefundViewSet, basename='orderrefund')

# Stripe webhook endpoint (must be added to urlpatterns)
stripe_urls = [
    path('stripe/webhook/', stripe_webhook, name='stripe-webhook'),
    path('stripe/create-intent/<uuid:cart_id>/', create_payment_intent, name='create-payment-intent'),
]

shop_url_patterns = [
    path('', include(shop.urls)),          # include all router endpoints
    *stripe_urls,                          # unpack stripe urls
]