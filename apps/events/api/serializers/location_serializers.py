from rest_framework import serializers
from apps.events.models import *
from apps.users.api.serializers import SimplifiedCommunityUserSerializer
from django_countries.serializers import CountryFieldMixin

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
    # get chapter heads names
    youth_chapter_heads = SimplifiedCommunityUserSerializer(many=True, read_only=True)
    adult_coordinators = SimplifiedCommunityUserSerializer(many=True, read_only=True)
    
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
        
class SimplifiedAreaLocationSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.unit_name', read_only=True)
    chapter_name = serializers.CharField(source='unit.chapter.chapter_name', read_only=True)
    cluster_name = serializers.CharField(source='unit.chapter.cluster.cluster_id', read_only=True)
    country_name = serializers.CharField(source='unit.chapter.cluster.world_location.country.name', read_only=True)
    
    class Meta:
        model = AreaLocation
        fields = ("unit_name", "chapter_name", "cluster_name", "country_name", "id", "area_id", "area_name" ,"area_code")
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
        
class SearchAreaSupportLocationSerializer(serializers.ModelSerializer):
    relative_area_name = serializers.CharField(source="relative_area.name", read_only=True)

    class Meta:
        model = SearchAreaSupportLocation
        fields = ["id", "name", "relative_area", "relative_area_name"]


class EventVenueSerializer(serializers.ModelSerializer):
    general_area_name = serializers.CharField(source="general_area.name", read_only=True)

    class Meta:
        model = EventVenue
        fields = [
            "id",
            "name",
            "address_line_1",
            "address_line_2",
            "address_line_3",
            "postcode",
            "max_allowed_people",
            "venue_type",
            "general_area",
            "general_area_name",
            "primary_venue",
            "contact_phone_number",
        ]