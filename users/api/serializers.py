# serializers.py
from rest_framework import serializers
from users.models import (
    CommunityUser, CommunityRole, UserCommunityRole
)
from django.utils.translation import gettext_lazy as _

class CommunityRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityRole
        fields = '__all__'

class UserCommunityRoleSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.get_role_name_display', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = UserCommunityRole
        fields = '__all__'

class CommunityUserSerializer(serializers.ModelSerializer):
    roles = UserCommunityRoleSerializer(source='role_links', many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    short_name = serializers.CharField(source='get_short_name', read_only=True)
    
    class Meta:
        model = CommunityUser
        fields = '__all__'
        extra_kwargs = {
            'password': {'write_only': True},
            'member_id': {'read_only': True},
            'username': {'read_only': True},
        }
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = CommunityUser.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

class SimplifiedCommunityUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityUser
        fields = ('id', 'member_id', 'first_name', 'last_name', 'ministry')