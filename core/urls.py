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

from users.api.views import *
from events.api.views import (
    # location viewsets
    CountryLocationViewSet, ClusterLocationViewSet, ChapterLocationViewSet,
    UnitLocationViewSet, AreaLocationViewSet, SearchAreaSupportLocationViewSet, EventVenueViewSet,
    # event viewsets
    EventViewSet, EventParticipantViewSet, EventRoleViewSet, EventServiceTeamMemberViewSet,
    PublicEventResourceViewSet,
    # payment viewsets
    EventPaymentMethodViewSet, EventPaymentPackageViewSet, EventPaymentViewSet,
    # registration viewsets
    ExtraQuestionViewSet, QuestionChoiceViewSet, QuestionAnswerViewSet,
)

'''
ROUTERS
'''
user_router = DefaultRouter()
user_router.register(r'', CommunityUserViewSet)
user_router.register(r"reg/extra-questions", ExtraQuestionViewSet)
user_router.register(r"reg/question-choices", QuestionChoiceViewSet)
user_router.register(r"reg/question-answers", QuestionAnswerViewSet)
user_router.register(r"alergies", AlergiesViewSet)
user_router.register(r"medical-conditions", MedicalConditionsViewSet)
user_router.register(r"emergency-contacts", EmergencyContactViewSet)

role_router = DefaultRouter()
role_router.register(r'community-roles', CommunityRoleViewSet)
role_router.register(r'user-roles', UserCommunityRoleViewSet)

location_router = DefaultRouter()
location_router.register(r'countries', CountryLocationViewSet)
location_router.register(r'clusters', ClusterLocationViewSet)
location_router.register(r'chapters', ChapterLocationViewSet)
location_router.register(r'units', UnitLocationViewSet)
location_router.register(r'areas', AreaLocationViewSet)
location_router.register(r"search-areas", SearchAreaSupportLocationViewSet, basename="searcharea")

event_router = DefaultRouter()

event_router.register(r'events', EventViewSet)
event_router.register(r'event-service-team', EventServiceTeamMemberViewSet)
event_router.register(r'event-roles', EventRoleViewSet)
event_router.register(r'event-participants', EventParticipantViewSet)
event_router.register(r"public-event-resources", PublicEventResourceViewSet)
location_router.register(r"event-venues", EventVenueViewSet, basename="eventvenue")

payment_routers = DefaultRouter()
payment_routers.register(r"event-payment-methods", EventPaymentMethodViewSet)
payment_routers.register(r"event-payment-packages", EventPaymentPackageViewSet)
payment_routers.register(r"event-payments", EventPaymentViewSet)

'''
SCHEMA
'''
    
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

'''
MAIN URL PATTERNS
'''

urlpatterns = [
    path("admin/", admin.site.urls),
    # Your existing API endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    path('api/location/', include(location_router.urls)),
    path('api/roles/', include(role_router.urls)),
    path('api/users/', include(user_router.urls)),
    path('api/events/', include(event_router.urls)),
    # Swagger and ReDoc documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'redoc', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)