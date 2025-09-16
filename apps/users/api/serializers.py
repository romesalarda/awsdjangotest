# serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import models

from apps.users.models import (
    CommunityUser, CommunityRole, UserCommunityRole,
    Allergy, MedicalCondition, EmergencyContact, UserAllergy, UserMedicalCondition
)

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
        
class SimplifiedUserCommunityRoleSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.get_role_name_display', read_only=True)
    
    class Meta:
        model = UserCommunityRole
        fields = ('role_name', 'start_date')
        
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


class AllergySerializer(serializers.ModelSerializer):
    """Base allergy definition (master data)."""

    class Meta:
        model = Allergy
        fields = ["id", "name", "description", "triggers", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class MedicalConditionSerializer(serializers.ModelSerializer):
    """Base medical condition definition (master data)."""

    class Meta:
        model = MedicalCondition
        fields = ["id", "name", "description", "triggers", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class UserAllergySerializer(serializers.ModelSerializer):
    allergy = AllergySerializer(read_only=True)
    allergy_id = serializers.PrimaryKeyRelatedField(
        queryset=Allergy.objects.all(), source="allergy", write_only=True
    )
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = UserAllergy
        fields = [
            "id", "user", "allergy", "allergy_id",
            "severity", "severity_display", "instructions", "notes",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserMedicalConditionSerializer(serializers.ModelSerializer):
    condition = MedicalConditionSerializer(read_only=True)
    condition_id = serializers.PrimaryKeyRelatedField(
        queryset=MedicalCondition.objects.all(), source="condition", write_only=True
    )
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = UserMedicalCondition
        fields = [
            "id", "user", "condition", "condition_id",
            "severity", "severity_display", "instructions", "date_diagnosed"
        ]
        read_only_fields = ["id"]
        
class SimpleAllergySerializer(serializers.ModelSerializer):
    # flatten instead of nesting user + full allergy model
    name = serializers.CharField(source="allergy.name", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = UserAllergy
        fields = ["id", "name", "severity", "severity_display", "instructions", "notes"]


class SimpleMedicalConditionSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="condition.name", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = UserMedicalCondition
        fields = ["id", "name", "severity", "severity_display", "instructions", "date_diagnosed"]


class SimpleEmergencyContactSerializer(serializers.ModelSerializer):
    contact_relationship_display = serializers.CharField(
        source="get_contact_relationship_display", read_only=True
    )

    class Meta:
        model = EmergencyContact
        fields = [
            "id", "first_name", "last_name", "phone_number",
            "contact_relationship", "contact_relationship_display", "is_primary"
        ]
        
# main serialiser

class CommunityUserSerializer(serializers.ModelSerializer):
    '''
    Main serializer for CommunityUser model
    '''
    roles = SimplifiedUserCommunityRoleSerializer(source='role_links', many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    short_name = serializers.CharField(source='get_short_name', read_only=True)
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    emergency_contacts = SimpleEmergencyContactSerializer(
        source="community_user_emergency_contacts", many=True, read_only=True
    )
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    
    alergies = SimpleAllergySerializer(
        source="user_allergies", many=True, read_only=True
    )
    medical_conditions = SimpleMedicalConditionSerializer(
        source="user_medical_conditions", many=True, read_only=True
    )  
    
    class Meta:
        model = CommunityUser
        fields = ('member_id','roles', 'username', 'full_name', 'short_name','password', 'first_name', 'last_name', 'middle_name', 'preferred_name',
                  'primary_email', 'secondary_email', 'phone_number', 'address_line_1', 'address_line_2', 'postcode', 'area_from',
                  'emergency_contacts', 'alergies', 'medical_conditions',)
        extra_kwargs = {
            'password': {'write_only': True},
            'member_id': {'read_only': True},
            'username': {'read_only': True},
        }
            
    def validate(self, attrs):
        first_name = attrs.get('first_name')
        last_name = attrs.get('last_name')
        password = attrs.get('password')
        errors = {}
        if not first_name or not last_name:
            errors["error"] = "First name and last name are required."
        if not password:
            errors["password"] = "Password is required for creating a user."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        
        if CommunityUser.objects.filter(
            first_name=validated_data.get('first_name'),
            last_name=validated_data.get('last_name'),
        ).exists():
            raise serializers.ValidationError("A user with the same first name and last name already exists.")

        user = CommunityUser.objects.create(**validated_data)
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
                "roles": rep.get("roles", []),
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


class ReducedMinistryType(models.TextChoices):
    
    VOLUNTEER = "VLN", _("Volunteer") # not looking to join the community but is attending an event e.g. a priest
    YOUTH_GUEST = "YGT", _("Youth Guest")
    ADULT_GUEST = "AGT", _("Adult Guest") 

class SimplifiedCommunityUserSerializer(serializers.ModelSerializer):
    
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    # age = serializers.IntegerField(source='get_age', write_only=True)
    data_of_birth = serializers.DateTimeField(source='date_of_birth', write_only=True)
    gender = serializers.ChoiceField(choices=CommunityUser.GenderType.choices, write_only=True)
    ministry = serializers.ChoiceField(choices=ReducedMinistryType.choices, write_only=True)
    
    class Meta:
        model = CommunityUser
        fields = ('member_id', 'first_name', 'last_name', 'ministry', 'password', 'gender', 'data_of_birth')

    def validate(self, attrs):
        first_name = attrs.get('first_name')
        last_name = attrs.get('last_name')
        password = attrs.get('password')
        errors = {}
        if not first_name or not last_name:
            errors["error"] = "First name and last name are required."
        if not password:
            errors["password"] = "Password is required for creating a user."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = CommunityUser.objects.create(**validated_data)
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

