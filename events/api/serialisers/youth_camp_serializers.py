from rest_framework import serializers
from events.models import *
from django_countries.serializers import CountryFieldMixin
from django.contrib.auth import get_user_model

User = get_user_model()

class YouthCampRoleSerializer(serializers.ModelSerializer):
    role_name_display = serializers.CharField(source='get_role_name_display', read_only=True)
    
    class Meta:
        model = YouthCampRole
        fields = '__all__'
        read_only_fields = ('id',)

class YouthCampServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    youth_camp_name = serializers.CharField(source='youth_camp.name', read_only=True)
    # roles_info = YouthCampRoleSerializer(source='roles', many=True, read_only=True)
    
    class Meta:
        model = YouthCampServiceTeamMember
        fields = ('user_name', 'user_email', 'youth_camp_name', 'assigned_by_name')
        read_only_fields = ('id', 'assigned_at')

class YouthCampSerializer(serializers.ModelSerializer):
    area_type_display = serializers.CharField(source='get_area_type_display', read_only=True)
    specific_area_name = serializers.CharField(source='specific_area.area_name', read_only=True)
    supervising_chapter_youth_head_name = serializers.CharField(
        source='supervising_chapter_youth_head.get_full_name', read_only=True,
        label="Supervising Youth Head"
    )
    supervising_chapter_CFC_coordinator_name = serializers.CharField(
        source='supervising_chapter_CFC_coordinator.get_full_name', read_only=True,
        label="CFC Coordinator"
    )
    duration_days = serializers.IntegerField(read_only=True)
    service_team_members = YouthCampServiceTeamMemberSerializer(
        many=True, read_only=True
    )
    areas_involved_list = serializers.SerializerMethodField()
    
    class Meta:
        model = YouthCamp
        fields = (
            'id', 'name', 'theme', 'anchor_verse', 'number_of_pax',
            'area_type_display', 'specific_area_name', 'service_team_members', 'duration_days', 'supervising_chapter_youth_head_name', 
            'supervising_chapter_CFC_coordinator_name', 'areas_involved_list'
            )
        read_only_fields = ('id', 'specific_area_name')
    
    def get_areas_involved_list(self, obj):
        return [{'id': area.id, 'name': area.area_name} for area in obj.areas_involved.all()]

# Nested serializers for detailed views
class NestedYouthCampServiceTeamMemberSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    roles_info = YouthCampRoleSerializer(source='roles', many=True, read_only=True)
    
    class Meta:
        model = YouthCampServiceTeamMember
        fields = ('id', 'user_info', 'roles_info', 'head_of_role', 'assigned_at', 'assigned_by')
    
    def get_user_info(self, obj):
        return {
            'id': obj.user.id,
            'first_name': obj.user.get_full_name(),
            'email': obj.user.email
        }

class DetailedYouthCampSerializer(YouthCampSerializer):
    service_team_members = NestedYouthCampServiceTeamMemberSerializer(
        many=True, read_only=True
    )
    areas_involved_details = serializers.SerializerMethodField()
    
    class Meta(YouthCampSerializer.Meta):
        fields = "__all__"
    
    def get_areas_involved_details(self, obj):
        return [
            {
                'id': area.id,
                'name': area.area_name,
                'code': area.area_code,
                'unit': area.unit.unit_name if area.unit else None,
                'chapter': area.unit.chapter.chapter_name if area.unit and area.unit.chapter else None
            }
            for area in obj.areas_involved.all()
        ]