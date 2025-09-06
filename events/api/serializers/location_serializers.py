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