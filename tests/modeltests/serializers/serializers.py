# -*- coding: utf-8 -*-
from django.core.serializers import ObjectSerializer, Field
from .models import Article


class ShortField(Field):
    def serialized_value(self, obj, field_name):
        return getattr(obj, 'headline')[:10]

    def deserialized_value(self, obj, instance, field_name):
        pass


class NewField(Field):
    def serialized_value(self, obj, field_name):
        return "New field"
    
    def deserialized_value(self, obj, instance, field_name):
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
    pub_date = Field(attribute=True)
