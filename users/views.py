from rest_framework import generics, permissions
from .serialisers import UserSerializer
from rest_framework import viewsets, permissions

from django.contrib.auth import get_user_model

# class UserRegistrationView(generics.CreateAPIView):
#     permission_classes = [permissions.AllowAny]
#     serializer_class = UserSerializer

# class UserListCreateView(generics.ListCreateAPIView):
#     permission_classes = [permissions.AllowAny]
#     serializer_class = UserSerializer
    
#     def get_queryset(self):
#         return get_user_model().objects.all()

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = get_user_model().objects.all().order_by("first_name")
    serializer_class = UserSerializer
