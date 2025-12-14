from rest_framework.routers import DefaultRouter
from django.urls import path
from apps.users.api.views import *


user_router = DefaultRouter()
user_router.register(r'manage', CommunityUserViewSet)
user_router.register(r"alergies", AlergiesViewSet)
user_router.register(r"medical-conditions", MedicalConditionsViewSet)
user_router.register(r"emergency-contacts", EmergencyContactViewSet)

role_router = DefaultRouter()
role_router.register(r'community-roles', CommunityRoleViewSet)
role_router.register(r'user-roles', UserCommunityRoleViewSet)

# Health check endpoint for container monitoring
health_urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
]

