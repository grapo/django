# -*- coding: utf-8 -*-
from django.core.serializers import ModelSerializer, Field, ModelSerializer
from django.core.serializers.native import DumpdataSerializer
from django.core.serializers import field
from .models import Author, Article


class ShortField(Field):
    def serialize_object(self, obj):
        return getattr(obj, 'headline')[:10]

    def set_object(self, obj, instance, field_name):
        pass


class NewField(Field):
    def serialize_object(self, obj):
        return "New field"
    
    def set_object(self, obj, instance, field_name):
        pass
    

class ArticleSerializer(ModelSerializer):
    class Meta:
        class_name=Article


class CustomFieldsSerializer(ArticleSerializer):
    short_headline = ShortField()
    new_field = NewField()


class LabelSerializer(ArticleSerializer):
    headline = Field(label="title")


class AttributeSerializer(ArticleSerializer):
    pub_date = Field()

    def metadata(self, metadict):
        metadict['attributes'] = ['pub_date']
        return metadict


class FieldSerializer(ModelSerializer):
    author = DumpdataSerializer()
    categories = field.M2mField(related_field=DumpdataSerializer)


class NestedArticleSerializer(DumpdataSerializer):
    fields = FieldSerializer(follow_object=False)
