from django.contrib import admin

from django.urls import path
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework.routers import DefaultRouter

# from users.views import UserRegistrationView, UserListCreateView
from users.api.views import *
from events.api.views import (
    CountryLocationViewSet,
    ClusterLocationViewSet,
    ChapterLocationViewSet,
    UnitLocationViewSet,
    AreaLocationViewSet,
    EventViewSet, EventParticipantViewSet, EventRoleViewSet, EventServiceTeamMemberViewSet
)


router = DefaultRouter()
router.register(r'users', CommunityUserViewSet)
router.register(r'community-roles', CommunityRoleViewSet)
router.register(r'user-roles', UserCommunityRoleViewSet)
router.register(r'countries', CountryLocationViewSet)
router.register(r'clusters', ClusterLocationViewSet)
router.register(r'chapters', ChapterLocationViewSet)
router.register(r'units', UnitLocationViewSet)
router.register(r'areas', AreaLocationViewSet)
router.register(r'events', EventViewSet)
router.register(r'event-service-team', EventServiceTeamMemberViewSet)
router.register(r'event-roles', EventRoleViewSet)
router.register(r'event-participants', EventParticipantViewSet)

urlpatterns = [
    path('api/locations/', include(router.urls)),
]
    
# Swagger schema view
schema_view = get_schema_view(
    openapi.Info(
        title="PLayground API Application",
        default_version='v1',
        description="",
        terms_of_service="https://www.yourapp.com/terms/",
        contact=openapi.Contact(email="romxsalarda45@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path("admin/", admin.site.urls),
    # Your existing API endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/register/', UserRegistrationView.as_view(), name='register'),
    # path('api/users/', UserListCreateView.as_view(), name='users'),
    path('api/', include(router.urls)),

    # Swagger and ReDoc documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'redoc', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    # path('sentry-debug/', trigger_error)
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)