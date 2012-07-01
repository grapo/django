# -*- coding: utf-8 -*-
from django.core.serializers import ObjectSerializer, Field
from .models import Article


class ShortField(Field):
    def serialize_value(self, obj):
        return getattr(obj, 'headline')[:10]

    def set_object(self, obj, instance, field_name):
        pass


class NewField(Field):
    def serialize_value(self, obj):
        return "New field"
    
    def set_object(self, obj, instance, field_name):
        pass
    

class ArticleSerializer(ObjectSerializer):
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
