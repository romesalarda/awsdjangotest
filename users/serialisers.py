from rest_framework import serializers
from django.contrib.auth import get_user_model 


class UserSerializer(serializers.ModelSerializer):
    
    password = serializers.CharField(required=True, write_only=True)
    
    class Meta:
        model = get_user_model()
        fields = ("username", "password")

    def create(self, validated_data):
        user = get_user_model().objects.create_user(**validated_data)
        user.save()
        return user 