from rest_framework.routers import DefaultRouter
from users.api.views import *


user_router = DefaultRouter()
user_router.register(r'manage', CommunityUserViewSet)
user_router.register(r"alergies", AlergiesViewSet)
user_router.register(r"medical-conditions", MedicalConditionsViewSet)
user_router.register(r"emergency-contacts", EmergencyContactViewSet)

role_router = DefaultRouter()
role_router.register(r'community-roles', CommunityRoleViewSet)
role_router.register(r'user-roles', UserCommunityRoleViewSet)
