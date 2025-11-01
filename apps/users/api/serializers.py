# serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import models, transaction

from apps.users.models import (
    CommunityUser, CommunityRole, UserCommunityRole,
    Allergy, MedicalCondition, EmergencyContact, UserAllergy, UserMedicalCondition
)
from apps.events.models import AreaLocation

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
    
    def update(self, instance, validated_data):
        allergy_data = validated_data.pop('allergy', {})
        allergy_name = allergy_data.get('name')
        user = validated_data.pop('user', self.context.get('user'))
        if not user:
            raise serializers.ValidationError("User is required to update a UserAllergy.")
        allergy, created = Allergy.objects.get_or_create(name=allergy_name)
        if UserAllergy.objects.filter(user=user, allergy=allergy).exclude(id=instance.id).exists():
            raise serializers.ValidationError("This allergy is already linked to the user.")
        validated_data['user'] = user
        validated_data['allergy'] = allergy
        return super().update(instance, validated_data)


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
    
    def update(self, instance, validated_data):
        condition_data = validated_data.pop('condition', {})
        condition_name = condition_data.get('name')
        user = validated_data.pop('user', self.context.get('user'))
        if not user:
            raise serializers.ValidationError("User is required to update a UserMedicalCondition.")
        condition, created = MedicalCondition.objects.get_or_create(name=condition_name)
        if UserMedicalCondition.objects.filter(user=user, condition=condition).exclude(id=instance.id).exists():
            raise serializers.ValidationError("This medical condition is already linked to the user.")
        validated_data['user'] = user
        validated_data['condition'] = condition
        return super().update(instance, validated_data)


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
    username = serializers.CharField(required=False, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    short_name = serializers.CharField(source='get_short_name', read_only=True)
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    emergency_contacts = SimpleEmergencyContactSerializer(
        source="community_user_emergency_contacts", many=True, read_only=True
    )
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    
    alergies = SimpleAllergySerializer(
        source="user_allergies", many=True, read_only=True
    )
    medical_conditions = SimpleMedicalConditionSerializer(
        source="user_medical_conditions", many=True, read_only=True
    )
    
    # Write-only fields for nested data updates
    emergency_contacts_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of emergency contact dicts for creation/update"
    )
    allergies_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of allergy dicts for creation/update"
    )
    medical_conditions_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of medical condition dicts for creation/update"
    )
    roles_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of community role assignment dicts for creation/update"
    )  
    
    area_full_display = serializers.CharField(source="area_from", read_only=True)
    area_from_display = serializers.SerializerMethodField()
    chapter = serializers.SerializerMethodField()
    cluster = serializers.SerializerMethodField()
        
    class Meta:
        model = CommunityUser
        fields = ('member_id','roles', 'id', 'username', 'full_name', 'short_name','password', 'first_name', 'last_name', 'middle_name', 'preferred_name',
                  'primary_email', 'secondary_email', 'phone_number', 'address_line_1', 'address_line_2', 'postcode', 'area_from',
                  'emergency_contacts', 'alergies', 'medical_conditions', "is_encoder", "is_active", "date_of_birth", 
                  'gender', 'age', 'marital_status', 'blood_type', 'ministry', 
                  'profile_picture', 'profile_picture_uploaded_at', 'last_login', 'user_uploaded_at',
                  "chapter", "cluster", "area_from_display", "area_full_display",
                  # Write-only nested data fields
                  'emergency_contacts_data', 'allergies_data', 'medical_conditions_data', 'roles_data')
        extra_kwargs = {
            'password': {'write_only': True},
            'member_id': {'read_only': True},
            'username': {'read_only': True},
            'area_from': {'required': False, 'allow_null': True},
            'gender': {'required': False},
        }
        
        
    def get_area_from_display(self, user):
        area_from = getattr(user, "area_from")
        if area_from is None:
            return 
        return area_from.area_name
    
    def get_chapter(self, user):
        area_from = getattr(user, "area_from")
        if area_from is None:
            return 
        return area_from.unit.chapter.chapter_name
    
    def get_cluster(self, user):
        area_from = getattr(user, "area_from")
        if area_from is None:
            return 
        return area_from.unit.chapter.cluster.cluster_id



    def to_internal_value(self, data):
        # Handle nested data structures sent from frontend
        
        # Handle identity nested structure
        if 'identity' in data:
            identity_data = data.pop('identity')
            for key, value in identity_data.items():
                data[key] = value
        
        # Handle contact nested structure
        if 'contact' in data:
            contact_data = data.pop('contact')
            # Handle nested address structure
            if 'address' in contact_data:
                address_data = contact_data.pop('address')
                for key, value in address_data.items():
                    contact_data[key] = value
            for key, value in contact_data.items():
                data[key] = value
        
        # Handle community nested structure
        if 'community' in data:
            community_data = data.pop('community')
            for key, value in community_data.items():
                data[key] = value
        
        # Handle safeguarding nested structure
        if 'safeguarding' in data:
            safeguarding_data = data.pop('safeguarding')
            # Map nested field names to expected field names
            if 'emergency_contacts' in safeguarding_data:
                data['emergency_contacts_data'] = safeguarding_data.pop('emergency_contacts')
            if 'allergies' in safeguarding_data:
                data['allergies_data'] = safeguarding_data.pop('allergies')
            if 'medical_conditions' in safeguarding_data:
                data['medical_conditions_data'] = safeguarding_data.pop('medical_conditions')
            
            for key, value in safeguarding_data.items():
                data[key] = value
        
        return super().to_internal_value(data)
            
    def validate(self, attrs):
        first_name = attrs.get('first_name')
        last_name = attrs.get('last_name')
        password = attrs.get('password')
        errors = {}
        
        # Basic field validation
        # For creation: both names are required
        if not self.instance and (not first_name or not last_name):
            errors["name"] = "First name and last name are required."
        
        # For updates: if name fields are provided, they can't be empty
        if self.instance:
            if first_name is not None and not first_name.strip():
                errors["first_name"] = "First name cannot be empty."
            if last_name is not None and not last_name.strip():
                errors["last_name"] = "Last name cannot be empty."
        
        # Password is only required for creation, not updates
        if not self.instance and not password:
            errors["password"] = "Password is required for creating a user."
        
        # Validate nested data if present
        emergency_contacts_data = attrs.get('emergency_contacts_data', [])
        allergies_data = attrs.get('allergies_data', [])
        medical_conditions_data = attrs.get('medical_conditions_data', [])
        
        # Validate emergency contacts
        if emergency_contacts_data:
            for i, contact_data in enumerate(emergency_contacts_data):
                if not contact_data.get('first_name') or not contact_data.get('last_name'):
                    errors[f"emergency_contacts[{i}]"] = "Emergency contact must have first name and last name."
                if not contact_data.get('phone_number'):
                    errors[f"emergency_contacts[{i}]"] = "Emergency contact must have a phone number."
        
        # Validate allergies
        if allergies_data:
            for i, allergy_data in enumerate(allergies_data):
                if not allergy_data.get('allergy_name') and not allergy_data.get('name'):
                    errors[f"allergies[{i}]"] = "Allergy must have a name."
                severity = allergy_data.get('severity')
                if severity and severity not in ['MILD', 'MODERATE', 'SEVERE', 'LIFE_THREATENING']:
                    errors[f"allergies[{i}]"] = "Invalid severity level. Must be MILD, MODERATE, SEVERE, or LIFE_THREATENING."
        
        # Validate medical conditions
        if medical_conditions_data:
            for i, condition_data in enumerate(medical_conditions_data):
                if not condition_data.get('condition_name') and not condition_data.get('name'):
                    errors[f"medical_conditions[{i}]"] = "Medical condition must have a name."
                severity = condition_data.get('severity')
                if severity and severity not in ['MILD', 'MODERATE', 'SEVERE', 'LIFE_THREATENING']:
                    errors[f"medical_conditions[{i}]"] = "Invalid severity level. Must be MILD, MODERATE, SEVERE, or LIFE_THREATENING."
        
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        # Extract nested relationship data
        print("attempting to create user")
        password = validated_data.pop('password', None)
        emergency_contacts_data = validated_data.pop('emergency_contacts_data', [])
        allergies_data = validated_data.pop('allergies_data', [])
        medical_conditions_data = validated_data.pop('medical_conditions_data', [])
        roles_data = validated_data.pop('roles_data', [])
        print("validated data", validated_data)
        if not validated_data.get("secondary_email"):
            validated_data.pop("secondary_email")
            
        with transaction.atomic():
            # Create the main user
            user = CommunityUser.objects.create(**validated_data)
            if password:
                user.set_password(password)
                user.save()
            
            # Handle Emergency Contacts creation
            if emergency_contacts_data:
                for contact_data in emergency_contacts_data:
                    contact_data['user'] = user.id
                    contact_serializer = EmergencyContactSerializer(data=contact_data)
                    if contact_serializer.is_valid(raise_exception=True):
                        contact_serializer.save()
            
            # Handle Allergies creation
            if allergies_data:
                for allergy_data in allergies_data:
                    # Normalize field names - handle both 'name' and 'allergy_name'
                    if 'name' in allergy_data and 'allergy_name' not in allergy_data:
                        allergy_data['allergy_name'] = allergy_data.pop('name')
                    
                    allergy_data['user'] = user.id
                    allergy_serializer = SimpleAllergySerializer(
                        data=allergy_data,
                        context={'user': user}
                    )
                    if allergy_serializer.is_valid(raise_exception=True):
                        allergy_serializer.save()
            
            # Handle Medical Conditions creation
            if medical_conditions_data:
                for condition_data in medical_conditions_data:
                    # Normalize field names - handle both 'name' and 'condition_name'
                    if 'name' in condition_data and 'condition_name' not in condition_data:
                        condition_data['condition_name'] = condition_data.pop('name')
                    
                    condition_data['user'] = user.id
                    condition_serializer = SimpleMedicalConditionSerializer(
                        data=condition_data,
                        context={'user': user}
                    )
                    if condition_serializer.is_valid(raise_exception=True):
                        condition_serializer.save()
            
            # Handle Community Roles creation
            if roles_data:
                for role_data in roles_data:
                    role_data['user'] = user.id
                    # Handle role_id field for new assignments
                    if 'role_id' in role_data:
                        role_data['role'] = role_data.pop('role_id')
                    
                    role_serializer = UserCommunityRoleSerializer(data=role_data)
                    if role_serializer.is_valid(raise_exception=True):
                        role_serializer.save()
            
        return user
    
    def update(self, instance, validated_data):
        # Extract nested relationship data
        password = validated_data.pop('password', None)
        emergency_contacts_data = validated_data.pop('emergency_contacts_data', None)
        allergies_data = validated_data.pop('allergies_data', None)
        medical_conditions_data = validated_data.pop('medical_conditions_data', None)
        roles_data = validated_data.pop('roles_data', None)
        
        with transaction.atomic():
            # Update basic user fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            
            # Handle password update
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
                "id":rep["id"],
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
                    "area_from_display": rep.get("area_from_display"),
                    "area_full_display": rep.get("area_full_display"),
                    "chapter": rep.get("chapter"),
                    "cluster": rep.get("cluster")
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


class ProfileUpdateSerializer(serializers.ModelSerializer):
    '''
    Dedicated serializer for user profile updates via PATCH requests.
    Supports updating basic profile information, profile picture, and safeguarding data.
    '''
    area_from_id = serializers.PrimaryKeyRelatedField(
        queryset=AreaLocation.objects.all(),
        source='area_from',
        write_only=True,
        required=False,
        allow_null=True
    )
    
    # Write-only fields for nested safeguarding data
    emergency_contacts_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    allergies_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    medical_conditions_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = CommunityUser
        fields = (
            'first_name', 'last_name', 'middle_name', 'preferred_name',
            'primary_email', 'secondary_email', 'phone_number',
            'address_line_1', 'address_line_2', 'postcode',
            'area_from', 'area_from_id', 'gender', 'date_of_birth',
            'marital_status', 'blood_type', 'ministry', 'profile_picture',
            'emergency_contacts_data', 'allergies_data', 'medical_conditions_data'
        )
        extra_kwargs = {
            'area_from': {'read_only': True},
            'profile_picture': {'required': False},
            'gender': {'required': False, 'allow_null': True},
            'marital_status': {'required': False, 'allow_null': True},
            'blood_type': {'required': False, 'allow_null': True},
            'ministry': {'required': False},
        }
    
    def validate_area_from_id(self, value):
        """Validate that the area location exists and is active."""
        if value and not value.active:
            raise serializers.ValidationError("Selected area is not active.")
        return value
    
    def validate_primary_email(self, value):
        """Ensure primary email is unique (excluding current user)."""
        if value:
            existing = CommunityUser.objects.filter(primary_email=value).exclude(id=self.instance.id if self.instance else None)
            if existing.exists():
                raise serializers.ValidationError("This email address is already in use.")
        return value
    
    def validate_secondary_email(self, value):
        """Ensure secondary email is unique (excluding current user)."""
        if value:
            existing = CommunityUser.objects.filter(secondary_email=value).exclude(id=self.instance.id if self.instance else None)
            if existing.exists():
                raise serializers.ValidationError("This email address is already in use.")
        return value
    
    def validate(self, attrs):
        """Cross-field validation with normalized error messages."""
        errors = {}
        
        # Ensure primary and secondary emails are different
        primary = attrs.get('primary_email') or (self.instance.primary_email if self.instance else None)
        secondary = attrs.get('secondary_email') or (self.instance.secondary_email if self.instance else None)
        gender = attrs.get("gender",None)
        if gender and isinstance(gender, str):
            attrs["gender"] = gender.upper()
        if primary and secondary and primary == secondary:
            errors['secondary_email'] = "Secondary email must be different from primary email."
        
        # Normalize empty string choices to None or skip
        # Only pop if the value is truly empty (empty string, None, or whitespace-only)
        for choice_field in ['gender', 'marital_status', 'blood_type', 'ministry']:
            if choice_field in attrs:
                value = attrs[choice_field]
                # Check if value is None, empty string, or whitespace-only string
                if value is None or (isinstance(value, str) and value.strip() == ''):
                    # Remove empty updates to avoid invalid choice errors and keep existing value
                    attrs.pop(choice_field)
        
        if errors:
            raise serializers.ValidationError({"errors": errors})

        return attrs
    
    def update(self, instance, validated_data):
        """Update user profile fields including nested safeguarding data."""
        # Extract nested data
        emergency_contacts_data = validated_data.pop('emergency_contacts_data', None)
        allergies_data = validated_data.pop('allergies_data', None)
        medical_conditions_data = validated_data.pop('medical_conditions_data', None)
        
        with transaction.atomic():
            # Update basic fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            
            # Update emergency contacts
            if emergency_contacts_data is not None:
                # Delete existing contacts
                instance.community_user_emergency_contacts.all().delete()
                # Create new contacts
                for contact_data in emergency_contacts_data:
                    EmergencyContact.objects.create(
                        user=instance,
                        first_name=contact_data.get('first_name', ''),
                        last_name=contact_data.get('last_name', ''),
                        phone_number=contact_data.get('phone_number', ''),
                        contact_relationship=contact_data.get('contact_relationship', ''),
                        is_primary=contact_data.get('is_primary', False)
                    )
            
            # Update allergies
            if allergies_data is not None:
                # Delete existing allergies
                instance.user_allergies.all().delete()
                # Create new allergies
                for allergy_data in allergies_data:
                    # Get or create the allergy master data
                    allergy, _ = Allergy.objects.get_or_create(
                        name=allergy_data.get('name', ''),
                        defaults={'description': ''}
                    )
                    # Create the user allergy link
                    UserAllergy.objects.create(
                        user=instance,
                        allergy=allergy,
                        severity=allergy_data.get('severity', 'low'),
                        instructions=allergy_data.get('instructions', ''),
                        notes=allergy_data.get('notes', '')
                    )
            
            # Update medical conditions
            if medical_conditions_data is not None:
                # Delete existing conditions
                instance.user_medical_conditions.all().delete()
                # Create new conditions
                for condition_data in medical_conditions_data:
                    # Get or create the condition master data
                    condition, _ = MedicalCondition.objects.get_or_create(
                        name=condition_data.get('name', ''),
                        defaults={'description': ''}
                    )
                    # Create the user condition link
                    UserMedicalCondition.objects.create(
                        user=instance,
                        condition=condition,
                        severity=condition_data.get('severity', 'low'),
                        instructions=condition_data.get('instructions', ''),
                        date_diagnosed=condition_data.get('date_diagnosed') or None
                    )
        
        return instance

    def to_internal_value(self, data):
        """
        Accept nested payloads from the frontend in the same shape as the read representation:
        - identity.name.{first,last,middle,preferred}
        - identity.{gender,date_of_birth,marital_status,blood_type}
        - contact.{primary_email,secondary_email,phone_number}
        - contact.address.{line1,line2,postcode,area_from}
        - community.{ministry}
        """
        # Copy to mutable dict if QueryDict
        data = dict(data)

        # identity
        identity = data.pop('identity', None)
        if identity and isinstance(identity, dict):
            name = identity.get('name') or {}
            if isinstance(name, dict):
                if 'first' in name:
                    data['first_name'] = name.get('first')
                if 'last' in name:
                    data['last_name'] = name.get('last')
                if 'middle' in name:
                    data['middle_name'] = name.get('middle')
                if 'preferred' in name:
                    data['preferred_name'] = name.get('preferred')

            for k in ['gender', 'date_of_birth', 'marital_status', 'blood_type']:
                if k in identity:
                    data[k] = identity.get(k)

        # contact
        contact = data.pop('contact', None)
        if contact and isinstance(contact, dict):
            for k in ['primary_email', 'secondary_email', 'phone_number']:
                if k in contact:
                    data[k] = contact.get(k)

            address = contact.get('address') or {}
            if isinstance(address, dict):
                # map to model fields
                if 'line1' in address:
                    data['address_line_1'] = address.get('line1')
                if 'line2' in address:
                    data['address_line_2'] = address.get('line2')
                if 'postcode' in address:
                    data['postcode'] = address.get('postcode')
                # area selection can be provided as numeric id
                if 'area_from' in address and address.get('area_from') not in [None, '', 'null']:
                    data['area_from_id'] = address.get('area_from')

        # community
        community = data.pop('community', None)
        if community and isinstance(community, dict):
            if 'ministry' in community:
                data['ministry'] = community.get('ministry')
        
        # safeguarding
        safeguarding = data.pop('safeguarding', None)
        if safeguarding and isinstance(safeguarding, dict):
            if 'emergency_contacts' in safeguarding:
                data['emergency_contacts_data'] = safeguarding.get('emergency_contacts')
            if 'allergies' in safeguarding:
                data['allergies_data'] = safeguarding.get('allergies')
            if 'medical_conditions' in safeguarding:
                data['medical_conditions_data'] = safeguarding.get('medical_conditions')

        return super().to_internal_value(data)


class SimplifiedCommunityUserSerializer(serializers.ModelSerializer):
    '''
    Simplified Community User serializer for dropdowns, lists, and registration.
    
    This serializer handles the mapping of 'area' (frontend field) to 'area_from' (model field).
    Frontend should send 'area' as a UUID string, which will be converted to an AreaLocation instance.
    '''
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    date_of_birth = serializers.DateField(required=False)
    gender = serializers.ChoiceField(choices=CommunityUser.GenderType.choices, required=False)
    ministry = serializers.ChoiceField(choices=ReducedMinistryType.choices, required=False)
    area_from_display = serializers.SerializerMethodField()
    area = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    username = serializers.CharField(required=False, read_only=True)
    password = serializers.CharField(required=False, write_only=True, style={"input_type": "password"})
    primary_email = serializers.EmailField(required=False)

    class Meta:
        model = CommunityUser
        fields = ('id', 'first_name', 'last_name', 'ministry', 'gender', 'date_of_birth', 'member_id', 'username' ,            
                  "profile_picture", "area_from_display", "area_from", "primary_email", "password", "area", "phone_number")
        extra_kwargs = {
            'area_from': {'read_only': True},  # Read-only, use 'area' for writes
            'member_id': {'read_only': True},
        }

    def get_area_from_display(self, obj):
        """
        Return area information with chapter and cluster details.
        Returns None if user has no area assigned.
        """
        if obj.area_from:
            return {
                "area": obj.area_from.area_name,
                "chapter": obj.area_from.unit.chapter.chapter_name,
                "cluster": obj.area_from.unit.chapter.cluster.cluster_id,
            }
        return None

    def validate_area(self, value):
        """
        Validate and convert area identifier (UUID or name) to AreaLocation instance.
        Returns None if value is empty/null.
        """
        if not value or value == '':
            return None
        
        try:
            # Import here to avoid circular imports
            from apps.events.models import AreaLocation
            import uuid
            
            # Try to parse as UUID first
            try:
                uuid.UUID(value)
                # It's a valid UUID, look up by ID
                area_location = AreaLocation.objects.get(id=value)
                return area_location
            except (ValueError, TypeError):
                # Not a UUID, try looking up by area_name
                area_location = AreaLocation.objects.get(area_name__iexact=value)
                return area_location
                
        except AreaLocation.DoesNotExist:
            raise serializers.ValidationError(f"Area location '{value}' does not exist.")
        except Exception as e:
            raise serializers.ValidationError(f"Error validating area: {str(e)}")

    def validate(self, attrs):
        """
        Cross-field validation and data transformation.
        Maps 'area' to 'area_from' for model compatibility.
        """
        # Handle area -> area_from mapping
        if 'area' in attrs:
            area_value = attrs.pop('area')
            if area_value is not None:
                # area_value is already validated and converted to AreaLocation instance
                attrs['area_from'] = area_value
            else:
                attrs['area_from'] = None
        
        # Ensure required fields for creation only (not for updates/partial updates)
        if not self.instance and not self.partial:
            # Creating a new user
            if not attrs.get('first_name'):
                raise serializers.ValidationError({"first_name": "First name is required."})
            if not attrs.get('last_name'):
                raise serializers.ValidationError({"last_name": "Last name is required."})
            if not attrs.get('primary_email'):
                raise serializers.ValidationError({"primary_email": "Email is required."})
            if not attrs.get('password'):
                raise serializers.ValidationError({"password": "Password is required."})
        
        return attrs
    
    def create(self, validated_data):
        """
        Create a new CommunityUser instance.
        Handles password hashing and automatic username/member_id generation.
        """
        # Extract password before creating user
        password = validated_data.pop('password', None)
        
        # Create user instance (username and member_id are auto-generated in model.save())
        instance = CommunityUser.objects.create(**validated_data)
        
        # Set password using Django's password hashing
        if password:
            instance.set_password(password)
            instance.save()
        
        return instance
        
    def update(self, instance, validated_data):
        """
        Update an existing CommunityUser instance.
        Only updates provided fields, handles password hashing if password is updated.
        """
        # Extract password if being updated
        password = validated_data.pop('password', None)
        
        # Update all other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle password update separately with hashing
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance

