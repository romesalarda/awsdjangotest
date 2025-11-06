from rest_framework import serializers
from apps.events.models import Organisation, OrganisationSocialMediaLink


class OrganisationSocialMediaLinkSerializer(serializers.ModelSerializer):
    """
    Serializer for OrganisationSocialMediaLink model.
    
    Handles social media links associated with organisations, including:
    - Platform name (e.g., Facebook, Instagram, Twitter)
    - External link to the social media profile
    - Optional description for the link
    
    Example API object:
    {
        "name": "Facebook",
        "external_link": "https://facebook.com/organisation-name",
        "description": "Official Facebook page for updates and events",
        "organisation": "123e4567-e89b-12d3-a456-426614174000"
    }
    """
    
    class Meta:
        model = OrganisationSocialMediaLink
        fields = [
            "id", "name", "external_link", "description", "organisation"
        ]
        read_only_fields = ("id",)
    
    def validate_external_link(self, value):
        """
        Validate that the external link is a valid URL.
        """
        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                "External link must be a valid URL starting with http:// or https://"
            )
        return value


class OrganisationSocialMediaLinkCreateSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for creating social media links within organisation context.
    Used for nested creation - organisation field is set automatically.
    
    Example API object (nested in organisation creation):
    {
        "name": "Instagram",
        "external_link": "https://instagram.com/organisation-handle",
        "description": "Follow us for daily updates"
    }
    """
    
    class Meta:
        model = OrganisationSocialMediaLink
        fields = ["name", "external_link", "description"]
    
    def validate_external_link(self, value):
        """Validate URL format"""
        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                "External link must be a valid URL starting with http:// or https://"
            )
        return value


class OrganisationSerializer(serializers.ModelSerializer):
    """
    Serializer for Organisation model with nested social media links.
    
    Handles organisation data including:
    - Basic information (name, description, contact)
    - Media assets (landing image, logo)
    - Social media links (nested creation/update)
    
    Example API object:
    {
        "name": "ANCOP International",
        "description": "Answering the Cry of the Poor - A foundation dedicated to serving the poor",
        "email": "contact@ancop.org",
        "external_link": "https://www.ancop.org",
        "landing_image": <file upload>,
        "logo": <file upload>,
        "social_media_links": [
            {
                "name": "Facebook",
                "external_link": "https://facebook.com/ancop",
                "description": "Official Facebook page"
            },
            {
                "name": "Instagram",
                "external_link": "https://instagram.com/ancop",
                "description": "Follow for updates"
            }
        ]
    }
    
    Response includes read-only fields:
    {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "ANCOP International",
        "description": "Answering the Cry of the Poor...",
        "landing_image": "https://example.com/media/organisations/landing-images/ancop.jpg",
        "landing_image_url": "https://example.com/media/organisations/landing-images/ancop.jpg",
        "logo": "https://example.com/media/organisations/logos/ancop-logo.png",
        "logo_url": "https://example.com/media/organisations/logos/ancop-logo.png",
        "email": "contact@ancop.org",
        "external_link": "https://www.ancop.org",
        "social_media_links": [...],
        "social_media_count": 2
    }
    """
    # Nested social media links for read operations
    social_media_links = OrganisationSocialMediaLinkSerializer(many=True, read_only=True)
    
    # Write-only field for creating/updating social media links
    social_media_data = OrganisationSocialMediaLinkCreateSerializer(
        many=True, 
        write_only=True, 
        required=False,
        help_text="List of social media link objects to create/update for this organisation"
    )
    
    # Additional computed fields
    social_media_count = serializers.SerializerMethodField()
    landing_image_url = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Organisation
        fields = [
            "id", "name", "description", "landing_image", "landing_image_url",
            "logo", "logo_url", "email", "external_link",
            "social_media_links", "social_media_data", "social_media_count"
        ]
        read_only_fields = ("id", "social_media_count", "landing_image_url", "logo_url")
    
    def get_social_media_count(self, obj):
        """Return count of associated social media links"""
        return obj.social_media_links.count()
    
    def get_landing_image_url(self, obj):
        """Get full URL for landing image"""
        if obj.landing_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.landing_image.url)
            return obj.landing_image.url
        return None
    
    def get_logo_url(self, obj):
        """Get full URL for logo"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None
    
    def validate_email(self, value):
        """Validate email format if provided"""
        if value and '@' not in value:
            raise serializers.ValidationError("Invalid email format")
        return value
    
    def validate_external_link(self, value):
        """Validate external link URL format if provided"""
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                "External link must be a valid URL starting with http:// or https://"
            )
        return value
    
    def create(self, validated_data):
        """
        Create organisation with nested social media links.
        
        Handles:
        - Organisation creation
        - Nested social media link creation
        - Proper relationship establishment
        """
        social_media_data = validated_data.pop('social_media_data', [])
        
        # Create the organisation
        organisation = Organisation.objects.create(**validated_data)
        
        # Create social media links
        for link_data in social_media_data:
            OrganisationSocialMediaLink.objects.create(
                organisation=organisation,
                **link_data
            )
        
        return organisation
    
    def update(self, instance, validated_data):
        """
        Update organisation with optional social media link updates.
        
        Handles:
        - Organisation field updates
        - Social media link replacement (removes old, adds new)
        - Partial updates (only provided fields are updated)
        """
        social_media_data = validated_data.pop('social_media_data', None)
        
        # Update organisation fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Handle social media links update if provided
        if social_media_data is not None:
            # Remove existing social media links
            instance.social_media_links.all().delete()
            
            # Create new social media links
            for link_data in social_media_data:
                OrganisationSocialMediaLink.objects.create(
                    organisation=instance,
                    **link_data
                )
        
        return instance


class OrganisationListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing organisations.
    Optimized for minimal data transfer in list views and dropdowns.
    
    Includes only essential fields for display and selection purposes.
    """
    social_media_count = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Organisation
        fields = [
            "id", "name", "description", "email", 
            "external_link", "logo_url", "social_media_count"
        ]
    
    def get_social_media_count(self, obj):
        """Return count of social media links"""
        return obj.social_media_links.count()
    
    def get_logo_url(self, obj):
        """Get full URL for logo"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None
