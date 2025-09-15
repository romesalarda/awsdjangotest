from django.contrib import admin

from django.urls import path
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from users.api.urls import *
from events.api.urls import *

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

    # path("location-admin/", LocationSite(name="location-admin").urls),
    # Your existing API endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    path('api/location/', include(location_router.urls)),
    path('api/roles/', include(role_router.urls)),
    path('api/users/', include(user_router.urls)),
    path('api/users/registration/', include(registration_router.urls)),
    path('api/events/', include(event_router.urls)),
    # Swagger and ReDoc documentation
    path('', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)