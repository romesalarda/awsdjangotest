from django.contrib import admin

from django.urls import path
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings

# Import secure authentication views instead of default JWT views
from apps.users.api.auth_views import (
    SecureTokenObtainView,
    SecureTokenRefreshView,
    SecureLogoutView,
    CSRFTokenView,
)

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from apps.users.api.urls import *
from apps.events.api.urls import *
from apps.shop.api.urls import *

'''
SCHEMA
'''
    
# Swagger schema view
schema_view = get_schema_view(
    openapi.Info(
        title="Catholic Events Management API - under construction",
        default_version='v1',
        description="",
        terms_of_service="https://www.yourapp.com/terms/",
        contact=openapi.Contact(email="romxsalarda45@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

'''
MAIN URL PATTERNS
'''

urlpatterns = [
    path("admin/", admin.site.urls),

    # Secure Authentication Endpoints (HTTPOnly Cookie-based)
    path('api/auth/login/', SecureTokenObtainView.as_view(), name='auth_login'),
    path('api/auth/refresh/', SecureTokenRefreshView.as_view(), name='auth_refresh'),
    path('api/auth/logout/', SecureLogoutView.as_view(), name='auth_logout'),
    path('api/auth/csrf/', CSRFTokenView.as_view(), name='auth_csrf'),
    
    # Legacy token endpoints (deprecated - redirect to new secure endpoints)
    path('api/token/', SecureTokenObtainView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', SecureTokenRefreshView.as_view(), name='token_refresh'),
    
    path('api/location/', include(location_router.urls)),
    path('api/roles/', include(role_router.urls)),
    path('api/users/', include(user_router.urls)),
    path('api/users/current/', CurrentUserView.as_view(), name='current-user'),
    path('api/events/', include(event_router.urls)),
    path('api/events/registration/', include(registration_router.urls)),
    path('api/events/payments/', include(payment_routers.urls)),
    path('api/organisations/', include(organisation_router.urls)),
    
    path('api/shop/', include(shop_url_patterns)),
    path('api/shop/metadata/', include(metadata.urls)),
    path('api/shop/payments/', include(production_payment_router.urls)),
    # Swagger and ReDoc documentation
    path('', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)