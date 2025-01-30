from rest_framework import generics, permissions
from .serialisers import UserSerializer

class UserRegistrationView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer
