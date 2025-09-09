# serializers.py
from rest_framework import serializers
from users.models import (
    CommunityUser, CommunityRole, UserCommunityRole,
    Alergies, MedicalConditions, EmergencyContact
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
    '''
    Main serializer for CommunityUser model
    '''
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
    
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_short_name(self, obj):
        return obj.preferred_name or obj.first_name
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)

        return {
            "identity": {
                "member_id": rep["member_id"],
                "username": rep["username"],
                "name": {
                    "full": self.get_full_name(instance),
                    "short": self.get_short_name(instance),
                    "first": rep["first_name"],
                    "last": rep["last_name"],
                    "middle": rep.get("middle_name"),
                    "preferred": rep.get("preferred_name"),
                },
                "gender": rep.get("gender"),
                "age": rep.get("age"),
                "date_of_birth": rep.get("date_of_birth"),
                "marital_status": rep.get("marital_status"),
                "blood_type": rep.get("blood_type"),
            },
            "contact": {
                "primary_email": rep.get("primary_email"),
                "secondary_email": rep.get("secondary_email"),
                "phone_number": rep.get("phone_number"),
                "address": {
                    "line1": rep.get("address_line_1"),
                    "line2": rep.get("address_line_2"),
                    "postcode": rep.get("postcode"),
                    "area_from": rep.get("area_from"),
                },
            },
            "community": {
                "ministry": rep.get("ministry"),
                "roles": rep.get("community_roles", []),
                "encoder": rep.get("is_encoder"),
                "active": rep.get("is_active"),
            },
            "profile": {
                "picture": rep.get("profile_picture"),
                "picture_uploaded_at": rep.get("profile_picture_uploaded_at"),
            },
            "safeguarding": {
                "alergies": rep.get("alergies", []),
                "medical_conditions": rep.get("medical_conditions", []),
                "emergency_contacts": rep.get("emergency_contacts", []),
            },
            "metadata": {
                "last_login": rep.get("last_login"),
                "uploaded_at": rep.get("user_uploaded_at"),
            },
        }

class SimplifiedCommunityUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityUser
        fields = ('member_id', 'first_name', 'last_name', 'ministry')


class AlergiesSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = Alergies
        fields = [
            "id", "name", "description", "instructions", "triggers",
            "severity", "severity_display", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MedicalConditionsSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = MedicalConditions
        fields = [
            "id", "name", "description", "instructions", "triggers",
            "severity", "severity_display", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmergencyContactSerializer(serializers.ModelSerializer):
    contact_relationship_display = serializers.CharField(source="get_contact_relationship_display", read_only=True)

    class Meta:
        model = EmergencyContact
        fields = [
            "id", "user", "first_name", "last_name", "middle_name",
            "preferred_name", "email", "phone_number", "secondary_phone",
            "contact_relationship", "contact_relationship_display",
            "address", "is_primary", "notes"
        ]
        read_only_fields = ["id"]
