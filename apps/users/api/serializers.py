# serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import models, transaction

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
    
    class Meta:
        model = CommunityUser
        fields = ('member_id','roles', 'username', 'full_name', 'short_name','password', 'first_name', 'last_name', 'middle_name', 'preferred_name',
                  'primary_email', 'secondary_email', 'phone_number', 'address_line_1', 'address_line_2', 'postcode', 'area_from',
                  'emergency_contacts', 'alergies', 'medical_conditions', "is_encoder",
                  # Write-only nested data fields
                  'emergency_contacts_data', 'allergies_data', 'medical_conditions_data', 'roles_data')
        extra_kwargs = {
            'password': {'write_only': True},
            'member_id': {'read_only': True},
            'username': {'read_only': True},
        }

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
        password = validated_data.pop('password', None)
        emergency_contacts_data = validated_data.pop('emergency_contacts_data', [])
        allergies_data = validated_data.pop('allergies_data', [])
        medical_conditions_data = validated_data.pop('medical_conditions_data', [])
        roles_data = validated_data.pop('roles_data', [])
        
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
        
        # print("UPDATE METHOD CALLED WITH DATA:", validated_data)
        """
        Update an existing CommunityUser instance with comprehensive nested relationship handling.
        
        This method handles complex updates including emergency contacts, allergies, medical conditions,
        and community roles. It supports both creating new related objects and updating existing ones.
        
        Example API request payload:
        {
            "identity": {
                "first_name": "Updated John",
                "last_name": "Updated Smith",
                "middle_name": "Updated Middle",
                "preferred_name": "Johnny Updated",
                "gender": "MALE",
                "date_of_birth": "1995-05-15",
                "marital_status": "SINGLE"
            },
            "contact": {
                "primary_email": "updated.john@example.com",
                "secondary_email": "updated.john.alt@example.com", 
                "phone_number": "+44 7700 900000",
                "address": {
                    "address_line_1": "Updated 123 Main Street",
                    "address_line_2": "Updated Apt 4B",
                    "postcode": "SW1A 1AA"
                }
            },
            "community": {
                "ministry": "YFC",
                "is_encoder": false,
                "roles": [
                    {
                        "role_id": "existing-role-uuid",  // Include ID to update existing
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                        "is_active": true,
                        "notes": "Updated role assignment"
                    },
                    {
                        // No ID = new role assignment
                        "role_id": "new-role-uuid",
                        "start_date": "2025-06-01",
                        "is_active": true
                    }
                ]
            },
            "safeguarding": {
                "emergency_contacts": [
                    {
                        "id": "existing-contact-uuid",  // Include ID to update existing
                        "first_name": "Updated Jane",
                        "last_name": "Updated Smith",
                        "phone_number": "+44 7700 900001",
                        "contact_relationship": "MOTHER",
                        "is_primary": true
                    },
                    {
                        // No ID = new emergency contact
                        "first_name": "New Contact",
                        "last_name": "Person",
                        "phone_number": "+44 7700 900002",
                        "contact_relationship": "FRIEND",
                        "is_primary": false
                    }
                ],
                "allergies": [
                    {
                        "id": "existing-allergy-link-uuid",  // UserAllergy ID to update existing
                        "allergy_name": "Peanuts",  // or allergy_id for existing allergy
                        "severity": "SEVERE",
                        "instructions": "Updated carry EpiPen at all times",
                        "notes": "Updated severe reaction"
                    },
                    {
                        // No ID = new allergy link
                        "allergy_name": "Shellfish",  // Creates new allergy if doesn't exist
                        "severity": "MODERATE",
                        "instructions": "Avoid all shellfish"
                    }
                ],
                "medical_conditions": [
                    {
                        "id": "existing-condition-link-uuid",  // UserMedicalCondition ID
                        "condition_name": "Asthma", // or condition_id for existing condition
                        "severity": "MODERATE",
                        "instructions": "Updated inhaler instructions",
                        "date_diagnosed": "2020-01-01"
                    },
                    {
                        // No ID = new medical condition link
                        "condition_name": "Type 1 Diabetes",
                        "severity": "SEVERE",
                        "instructions": "Monitor blood sugar regularly",
                        "date_diagnosed": "2021-06-15"
                    }
                ]
            },
            "password": "new_secure_password123"  // Optional password update
        }
        
        Alternative flat format (legacy support):
        {
            "first_name": "Updated John",
            "last_name": "Updated Smith",
            "primary_email": "updated.john@example.com",
            "emergency_contacts_data": [...],  // Alternative field name
            "allergies_data": [...],           // Alternative field name  
            "medical_conditions_data": [...],  // Alternative field name
            "roles_data": [...]                // Alternative field name
        }
        
        Key behaviors:
        - Emergency Contacts: CRUD operations - updates existing (with ID), creates new (no ID), deletes omitted
        - Allergies: CRUD operations on UserAllergy through model - same pattern
        - Medical Conditions: CRUD operations on UserMedicalCondition through model - same pattern
        - Community Roles: CRUD operations on UserCommunityRole through model - same pattern
        - Basic fields: Direct updates on the user instance
        - Password: Properly hashed using set_password() method
        - Validation: Ensures data integrity for all nested relationships
        """
        
        # Handle nested data structures sent from frontend
        if 'identity' in validated_data:
            identity_data = validated_data.pop('identity')
            for key, value in identity_data.items():
                validated_data[key] = value
        
        if 'contact' in validated_data:
            contact_data = validated_data.pop('contact')
            # Handle nested address structure
            if 'address' in contact_data:
                address_data = contact_data.pop('address')
                for key, value in address_data.items():
                    contact_data[key] = value
            for key, value in contact_data.items():
                validated_data[key] = value
        
        if 'community' in validated_data:
            community_data = validated_data.pop('community')
            for key, value in community_data.items():
                validated_data[key] = value
        
        if 'safeguarding' in validated_data:
            safeguarding_data = validated_data.pop('safeguarding')
            for key, value in safeguarding_data.items():
                validated_data[key] = value
        
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
            
            
            # Handle Emergency Contacts - CRUD operations
            if emergency_contacts_data is not None:
                existing_contacts = {str(contact.id): contact for contact in instance.community_user_emergency_contacts.all()}
                processed_ids = set()
                
                for contact_data in emergency_contacts_data:
                    contact_id = contact_data.get('id')          
                    relationship = contact_data.get('contact_relationship')
                    relationship = relationship.strip().upper() if relationship else None
                    # Validate relationship choice
                    if relationship and relationship not in dict(EmergencyContact.ContactRelationshipType.choices).keys():
                        raise serializers.ValidationError({
                            "error": f"Invalid contact relationship: {relationship} for contact {contact_data.get('first_name', '')} {contact_data.get('last_name', '')}."
                        })
                              
                    if contact_id and contact_id in existing_contacts:
                        # Update existing emergency contact
                        contact_serializer = EmergencyContactSerializer(
                            existing_contacts[contact_id],
                            data=contact_data,
                            partial=True
                        )
                        if contact_serializer.is_valid(raise_exception=True):
                            contact_serializer.save()
                            processed_ids.add(contact_id)
                    else:
                        # Create new emergency contact
                        contact_data['user'] = instance.id
                        contact_serializer = EmergencyContactSerializer(data=contact_data)
                        if contact_serializer.is_valid(raise_exception=True):
                            new_contact = contact_serializer.save()
                            processed_ids.add(new_contact.id)
                
                # Remove contacts that weren't in the update
                for contact_id, contact in existing_contacts.items():
                    if contact_id not in processed_ids:
                        contact.delete()
            # Handle Allergies - CRUD operations on UserAllergy through model
            if allergies_data is not None:
                existing_allergies = {str(allergy.id): allergy for allergy in instance.user_allergies.all()}
                processed_ids = set()
                for allergy_data in allergies_data:
                    allergy_id = allergy_data.get('id')
                    
                    if allergy_id and (allergy_id in [str(a) for a in existing_allergies.keys()]):
                        # Update existing UserAllergy
                        allergy_name = allergy_data.pop('allergy_name')
                        allergy_data['name'] = allergy_name
                        allergy_serializer = SimpleAllergySerializer(
                            existing_allergies[allergy_id],
                            data=allergy_data,
                            partial=True,
                            context={'user': instance}
                        )
                        if allergy_serializer.is_valid(raise_exception=True):
                            allergy_serializer.save()
                            processed_ids.add(allergy_id)
                    else:
                        # Create new UserAllergy
                        allergy_name = allergy_data.pop('allergy_name')
                        allergy_data['name'] = allergy_name
                        allergy_data['user'] = instance.id
                        allergy_serializer = SimpleAllergySerializer(
                            data=allergy_data,
                            context={'user': instance}
                        )
                        if allergy_serializer.is_valid(raise_exception=True):
                            new_allergy = allergy_serializer.save()
                            processed_ids.add(new_allergy.id)
                
                # Remove allergies that weren't in the update
                for allergy_id, allergy in existing_allergies.items():
                    if allergy_id not in processed_ids:
                        allergy.delete()
            # Handle Medical Conditions - CRUD operations on UserMedicalCondition through model
            if medical_conditions_data is not None:
                existing_conditions = {str(condition.id): condition for condition in instance.user_medical_conditions.all()}
                processed_ids = set()
                
                for condition_data in medical_conditions_data:
                    condition_id = condition_data.get('id')
                    severity = condition_data.get('severity')
                    severity = severity.strip().upper() if severity else None

                    if severity and severity not in dict(UserMedicalCondition.Severity.choices).keys():
                        raise serializers.ValidationError({
                            'severity': _('Invalid severity level.')
                        })

                    condition_data['severity'] = severity
                    if condition_id and condition_id in existing_conditions:
                        # Update existing UserMedicalCondition
                        condition_name = condition_data.pop('condition_name')
                        condition_data['name'] = condition_name
                        condition_serializer = SimpleMedicalConditionSerializer(
                            existing_conditions[condition_id],
                            data=condition_data,
                            partial=True,
                            context={'user': instance}
                        )
                        if condition_serializer.is_valid(raise_exception=True):
                            condition_serializer.save()
                            processed_ids.add(condition_id)
                    else:
                        # Create new UserMedicalCondition
                        condition_name = condition_data.pop('condition_name')
                        condition_data['name'] = condition_name

                        condition_data['user'] = instance.id
                        condition_serializer = SimpleMedicalConditionSerializer(
                            data=condition_data,
                            context={'user': instance}
                        )
                        if condition_serializer.is_valid(raise_exception=True):
                            new_condition = condition_serializer.save()
                            processed_ids.add(new_condition.id)
                
                # Remove medical conditions that weren't in the update
                for condition_id, condition in existing_conditions.items():
                    if condition_id not in processed_ids:
                        condition.delete()
            # Handle Community Roles - CRUD operations on UserCommunityRole through model
            if roles_data is not None:
                existing_roles = {str(role.id): role for role in instance.role_links.all()}
                processed_ids = set()
                
                for role_data in roles_data:
                    role_link_id = role_data.get('id')  # This is UserCommunityRole ID
                    
                    if role_link_id and role_link_id in existing_roles:
                        # Update existing UserCommunityRole
                        role_serializer = UserCommunityRoleSerializer(
                            existing_roles[role_link_id],
                            data=role_data,
                            partial=True
                        )
                        if role_serializer.is_valid(raise_exception=True):
                            role_serializer.save()
                            processed_ids.add(role_link_id)
                    else:
                        # Create new UserCommunityRole
                        role_data['user'] = instance.id
                        # Handle role_id field for new assignments
                        if 'role_id' in role_data:
                            role_data['role'] = role_data.pop('role_id')
                        
                        role_serializer = UserCommunityRoleSerializer(data=role_data)
                        if role_serializer.is_valid(raise_exception=True):
                            new_role = role_serializer.save()
                            processed_ids.add(new_role.id)
                
                # Remove role assignments that weren't in the update
                for role_id, role in existing_roles.items():
                    if role_id not in processed_ids:
                        role.delete()
            
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
        fields = ('first_name', 'last_name', 'ministry', 'gender', 'data_of_birth', 'member_id', 'username')
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

