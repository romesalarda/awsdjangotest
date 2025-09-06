from rest_framework import serializers
from events.models import *
from django_countries.serializers import CountryFieldMixin
from django.contrib.auth import get_user_model

class CountryLocationSerializer(CountryFieldMixin, serializers.ModelSerializer):
    class Meta:
        model = CountryLocation
        fields = '__all__'
        read_only_fields = ('id',)

class ClusterLocationSerializer(serializers.ModelSerializer):
    world_location_name = serializers.CharField(source='world_location.country.name', read_only=True)
    
    class Meta:
        model = ClusterLocation
        fields = '__all__'
        read_only_fields = ('id',)

class ChapterLocationSerializer(serializers.ModelSerializer):
    cluster_name = serializers.CharField(source='cluster.cluster_id', read_only=True)
    country_name = serializers.CharField(source='cluster.world_location.country.name', read_only=True)
    
    class Meta:
        model = ChapterLocation
        fields = '__all__'
        read_only_fields = ('id', 'chapter_id')

class UnitLocationSerializer(serializers.ModelSerializer):
    chapter_name = serializers.CharField(source='chapter.chapter_name', read_only=True)
    cluster_name = serializers.CharField(source='chapter.cluster.cluster_id', read_only=True)
    country_name = serializers.CharField(source='chapter.cluster.world_location.country.name', read_only=True)
    
    class Meta:
        model = UnitLocation
        fields = '__all__'
        read_only_fields = ('id', 'unit_id')

class AreaLocationSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.unit_name', read_only=True)
    chapter_name = serializers.CharField(source='unit.chapter.chapter_name', read_only=True)
    cluster_name = serializers.CharField(source='unit.chapter.cluster.cluster_id', read_only=True)
    country_name = serializers.CharField(source='unit.chapter.cluster.world_location.country.name', read_only=True)
    
    class Meta:
        model = AreaLocation
        fields = '__all__'
        read_only_fields = ('id', 'area_id')

# Nested serializers for hierarchical representation
class NestedAreaLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaLocation
        fields = ('id', 'area_id', 'area_name', 'area_code', 'general_address', 'location_description')

class NestedUnitLocationSerializer(serializers.ModelSerializer):
    areas = NestedAreaLocationSerializer(many=True, read_only=True)
    
    class Meta:
        model = UnitLocation
        fields = ('id', 'unit_id', 'unit_name', 'areas')

class NestedChapterLocationSerializer(serializers.ModelSerializer):
    units = NestedUnitLocationSerializer(many=True, read_only=True)
    
    class Meta:
        model = ChapterLocation
        fields = ('id', 'chapter_id', 'chapter_name', 'chapter_code', 'units')

class NestedClusterLocationSerializer(serializers.ModelSerializer):
    chapters = NestedChapterLocationSerializer(many=True, read_only=True)
    
    class Meta:
        model = ClusterLocation
        fields = ('id', 'cluster_id', 'chapters')

class NestedCountryLocationSerializer(serializers.ModelSerializer):
    clusters = NestedClusterLocationSerializer(many=True, read_only=True)
    
    class Meta:
        model = CountryLocation
        fields = ('id', 'country', 'general_sector', 'specific_sector', 'clusters')
        
# Youth Camp serialisers

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
    roles_info = YouthCampRoleSerializer(source='roles', many=True, read_only=True)
    
    class Meta:
        model = YouthCampServiceTeamMember
        fields = '__all__'
        read_only_fields = ('id', 'assigned_at')

class YouthCampSerializer(serializers.ModelSerializer):
    area_type_display = serializers.CharField(source='get_area_type_display', read_only=True)
    specific_area_name = serializers.CharField(source='specific_area.area_name', read_only=True)
    supervising_chapter_youth_head_name = serializers.CharField(
        source='supervising_chapter_youth_head.get_full_name', read_only=True
    )
    supervising_chapter_CFC_coordinator_name = serializers.CharField(
        source='supervising_chapter_CFC_coordinator.get_full_name', read_only=True
    )
    duration_days = serializers.IntegerField(read_only=True)
    service_team_members = YouthCampServiceTeamMemberSerializer(
        many=True, read_only=True
    )
    areas_involved_list = serializers.SerializerMethodField()
    
    class Meta:
        model = YouthCamp
        fields = "__all__"
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