# serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import models

from apps.users.models import (
    CommunityUser, CommunityRole, UserCommunityRole,
    Allergy, MedicalCondition, EmergencyContact, UserAllergy, UserMedicalCondition
)

class CommunityRoleSerializer(serializers.ModelSerializer):
    '''
    Serializer for community roles.
    '''
    class Meta:
        model = CommunityRole
        fields = '__all__'

class UserCommunityRoleSerializer(serializers.ModelSerializer):
    '''
    Serializer for user community roles.
    '''
    role_name = serializers.CharField(source='role.get_role_name_display', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = UserCommunityRole
        fields = '__all__'
        
class SimplifiedUserCommunityRoleSerializer(serializers.ModelSerializer):
    '''
    Simplified serializer for user roles.
    '''
    role_name = serializers.CharField(source='role.get_role_name_display', read_only=True)
    
    class Meta:
        model = UserCommunityRole
        fields = ('role_name', 'start_date')
        
class EmergencyContactSerializer(serializers.ModelSerializer):
    '''
    Serializer for emergency contacts.
    '''
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
    """
    Base medical condition definition (master data).
    """

    class Meta:
        model = MedicalCondition
        fields = ["id", "name", "description", "triggers", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class UserAllergySerializer(serializers.ModelSerializer):
    '''
    Through model serializer for user allergies.
    '''
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

    def validate(self, attrs): # ensure both allergy and user are present and unique together
        user = attrs.get('user') or self.instance.user if self.instance else None
        allergy = attrs.get('allergy') or self.instance.allergy if self.instance else None
        if not user or not allergy:
            raise serializers.ValidationError("Both user and allergy must be specified.")
        if UserAllergy.objects.exclude(id=self.instance.id if self.instance else None).filter(user=user, allergy=allergy).exists():
            raise serializers.ValidationError("This allergy is already linked to the user.")
        return super().validate(attrs)

class UserMedicalConditionSerializer(serializers.ModelSerializer):
    '''
    Through model serializer for user medical conditions.
    '''
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
    '''
    Simplified USER serializer for allergies.
    (THROUGH MODEL)
    '''
    name = serializers.CharField(source="allergy.name")
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    user = serializers.PrimaryKeyRelatedField(
        queryset=CommunityUser.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = UserAllergy
        fields = ["id", "name", "severity", "severity_display", "instructions", "notes", "user"]

    def create(self, validated_data):
        allergy_data = validated_data.pop('allergy', {})
        allergy_name = allergy_data.get('name')
        user = validated_data.pop('user', self.context.get('user'))
        if not user:
            raise serializers.ValidationError("User is required to create a UserAllergy.")  
        allergy, created = Allergy.objects.get_or_create(name=allergy_name)
        if UserAllergy.objects.filter(user=user, allergy=allergy).exists():
            raise serializers.ValidationError("This allergy is already linked to the user.")
        validated_data['user'] = user
        validated_data['allergy'] = allergy
        return super().create(validated_data)
    


class SimpleMedicalConditionSerializer(serializers.ModelSerializer):
    '''
    Simplified USER serializer for medical conditions.
    (THROUGH MODEL)
    '''
    name = serializers.CharField(source="condition.name")
    severity_display = serializers.CharField(source="get_severity_display", required=False)
    user = serializers.PrimaryKeyRelatedField(
        queryset=CommunityUser.objects.all(), write_only=True, required=False
    )
    class Meta:
        model = UserMedicalCondition
        fields = ["id", "name", "user", "severity", "severity_display", "instructions", "date_diagnosed"]

    def create(self, validated_data): # just ensure that user and condition are present
        condition_data = validated_data.pop('condition', {})
        condition_name = condition_data.get('name')
        user = validated_data.pop('user', self.context.get('user'))
        if not user:
            raise serializers.ValidationError("User is required to create a UserMedicalCondition.")
        condition, created = MedicalCondition.objects.get_or_create(name=condition_name)
        user_medical_condition = UserMedicalCondition.objects.create(condition=condition, user=user, **validated_data)
        return user_medical_condition
    
class SimpleEmergencyContactSerializer(serializers.ModelSerializer):
    '''
    Simplified USER serializer for emergency contacts.
    (THROUGH MODEL)
    '''
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
    Main serializer for CommunityUser model. Use this to create new users and view/edit existing users.
    For a simplified version and restrictive permissions (e.g. for dropdowns, lists, etc), use SimplifiedCommunityUserSerializer.
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
                  'emergency_contacts', 'alergies', 'medical_conditions', "is_encoder",)
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
    '''
    Simplified Community User serializer for dropdowns, lists, etc
    '''
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    data_of_birth = serializers.DateField(source='date_of_birth', required=False)
    gender = serializers.ChoiceField(choices=CommunityUser.GenderType.choices, required=False)
    ministry = serializers.ChoiceField(choices=ReducedMinistryType.choices, required=False)

    class Meta:
        model = CommunityUser
        fields = ('first_name', 'last_name', 'ministry', 'gender', 'data_of_birth')
        # member_id and password are excluded for safety

    def validate(self, attrs):
        # No required fields, so just return attrs
        return attrs

    def update(self, instance, validated_data):
        # Only update provided fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

