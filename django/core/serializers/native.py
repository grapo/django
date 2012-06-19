"""
Module for abstract serializer/unserializer base classes.
"""
from django.db import models

from django.core.serializers import base
from django.core.serializers import field

def make_options(options, **kwargs):
    for name in options.__dict__:
        attr = kwargs.get(name)
        if attr:
            setattr(options, name, attr)
    return options


class ObjectSerializerOptions(object):
    def __init__(self, options=None):
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.related_serializer = getattr(options, 'related_serializer', None)
        self.field_serializer = getattr(options, 'field_serializer', field.Field)
        self.related_reserialize = getattr(options, 'related_reserialize', None)
        self.class_name = getattr(options, 'class_name', None)


class ObjectSerializerMetaclass(base.SerializerMetaclass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ObjectSerializerMetaclass, cls).__new__(cls, name, bases, attrs)
        new_class._meta = ObjectSerializerOptions(getattr(new_class, 'Meta', None))
        return new_class


class BaseObjectSerializer(base.Serializer):
    def __init__(self, label=None, attribute=None, follow_object=True, **kwargs):
        super(BaseObjectSerializer, self).__init__(label, attribute, follow_object)
        self.opts = make_options(self._meta, **kwargs)

    def get_object_field_serializer(self, obj, field_name):
        return self.opts.field_serializer()

    def get_object_fields_names(self, obj):
        return obj.__dict__.keys()

    def get_fields_for_object(self, obj):
        declared_fields = super(BaseObjectSerializer, self).get_fields_for_object(obj)
        if self.opts.fields is not None and not self.opts.fields:
            return declared_fields
        declared_fields_names = declared_fields.keys()
        fields = {}
        fields_names = self.get_object_fields_names(obj)
        for f_name in fields_names:
            if self.opts.fields is not None and f_name not in self.opts.fields:
                continue
            if self.opts.exclude is not None and f_name in self.opts.exclude:
                continue
            if f_name in declared_fields_names:
                continue
            fields[f_name] = self.get_object_field_serializer(obj, f_name)
            
        fields.update(declared_fields)
        
        return fields
    
    def create_instance(self, obj):
        if self.opts.class_name is not None:
            if isinstance(self.opts.class_name, str):
                return _get_model(obj[self.opts.class_name])()
            else:
                return self.opts.class_name()
        raise base.DeserializationError(u"Can't resolve class for object creation")


class ObjectSerializer(BaseObjectSerializer):
    __metaclass__ = ObjectSerializerMetaclass


class ModelSerializer(ObjectSerializer):
    pass


def _get_model(model_identifier):
    """
    Helper to look up a model from an "app_label.module_name" string.
    """
    try:
        Model = models.get_model(*model_identifier.split("."))
    except TypeError:
        Model = None
    if Model is None:
        raise base.DeserializationError(u"Invalid model identifier: '%s'" % model_identifier)
    return Model
