from rest_framework import serializers
from django.contrib.auth import get_user_model 


class UserSerializer(serializers.ModelSerializer):
    
    ministry = serializers.ChoiceField(choices=get_user_model().MinistryType)
    username = serializers.CharField(read_only=True)
    password = serializers.CharField(required=False, write_only=True)
    
    class Meta:
        model = get_user_model()
        fields = ("id", "member_id","username", "password", "last_name", "first_name", "ministry")

    def create(self, validated_data):
        user = get_user_model().objects.create_user(**validated_data)
        user.save()
        return user 