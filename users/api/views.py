from rest_framework import generics, permissions
from .serialisers import UserSerializer, CommunityRoleSerialiser
from rest_framework import viewsets, permissions

from django.contrib.auth import get_user_model

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = get_user_model().objects.all().order_by("first_name")
    serializer_class = UserSerializer

class CommunityRoleViewset (viewsets.ModelViewSet):
    
    permission_classes = [permissions.AllowAny]
    queryset = CommunityRoleSerialiser.Meta.model.objects.all()
    serializer_class = CommunityRoleSerialiser