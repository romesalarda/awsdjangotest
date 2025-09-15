from rest_framework.routers import DefaultRouter
from shop.api.views.product_payment_views import (
    ProductPaymentMethodViewSet,
    ProductPaymentPackageViewSet,
    ProductPaymentViewSet,
)
from shop.api.views.shop_metadata_views import (
    ProductCategoryViewSet, 
    ProductMaterialViewSet,
    ProductImageViewSet,
)

from shop.api.views.shop_views import ( 
    EventProductViewSet,
    EventCartViewSet,
    EventProductOrderViewSet,   
)

production_payment_router = DefaultRouter()
production_payment_router.register(r'payment-methods', ProductPaymentMethodViewSet, basename='productpaymentmethod')
production_payment_router.register(r'payment-packages', ProductPaymentPackageViewSet, basename='productpaymentpackage')
production_payment_router.register(r'payments', ProductPaymentViewSet, basename='productpayment')

metadata = DefaultRouter()
metadata.register(r'categories', ProductCategoryViewSet, basename='productcategory')
metadata.register(r'materials', ProductMaterialViewSet, basename='productmaterial')
metadata.register(r'images', ProductImageViewSet, basename='productimage')

shop = DefaultRouter()
shop.register(r'products', EventProductViewSet, basename='eventproduct')
shop.register(r'carts', EventCartViewSet, basename='eventcart')
shop.register(r'orders', EventProductOrderViewSet, basename='eventproductorder')