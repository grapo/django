"""
Module for abstract serializer/unserializer base classes.
"""
from django.db import models
from django.utils.datastructures import SortedDict
import copy

from django.core.serializers import base
from django.core.serializers import field


def make_options(meta, **kwargs):
    options = copy.copy(meta)
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
    """
    Base class for serializing Python objects.
    """
    def __init__(self, label=None, follow_object=True, **kwargs):
        super(BaseObjectSerializer, self).__init__(label, follow_object)
        
        # possibility to override options when class is instantiated
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
        fields = SortedDict()
        fields_names = self.get_object_fields_names(obj)
        for f_name in fields_names:
            if self.opts.fields is not None and f_name not in self.opts.fields:
                continue
            if self.opts.exclude is not None and f_name in self.opts.exclude:
                continue
            if f_name in declared_fields_names:
                continue
            fields[f_name] = self.get_object_field_serializer(obj, f_name)
        declared_fields_copy = declared_fields.copy()
        declared_fields_copy.update(fields)
        if self.opts.fields: # ordering must be like in self.opts.fields
            serializable_fields = SortedDict()
            for name in self.opts.fields:
                item = declared_fields_copy.pop(name)
                if item is None:
                    raise base.SerializationError(u"")
                serializable_fields[name] = item
            serializable_fields.update(declared_fields_copy)
            return serializable_fields
        else: # declared first
            return declared_fields_copy

    def create_instance(self, serialized_obj):
        if self.opts.class_name is not None:
                return self.opts.class_name()
        raise base.DeserializationError(u"Can't resolve class for object creation")


class ObjectSerializer(BaseObjectSerializer):
    __metaclass__ = ObjectSerializerMetaclass


class ModelSerializerOptions(object):
    def __init__(self, options=None):
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.related_serializer = getattr(options, 'related_serializer', field.RelatedField)
        self.m2m_serializer = getattr(options, 'm2m_serializer', field.M2mField)
        self.field_serializer = getattr(options, 'field_serializer', field.ModelField)
        self.related_reserialize = getattr(options, 'related_reserialize', None)
        self.class_name = getattr(options, 'class_name', None)


class ModelSerializerMetaclass(base.SerializerMetaclass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ModelSerializerMetaclass, cls).__new__(cls, name, bases, attrs)
        new_class._meta = ModelSerializerOptions(getattr(new_class, 'Meta', None))
        return new_class


class BaseModelSerializer(BaseObjectSerializer):
    def get_object_field_serializer(self, obj, field_name):
        field, model, direct, m2m = obj._meta.get_field_by_name(field_name)
        if m2m:
            return self.opts.m2m_serializer()
        elif field.rel:
            return self.opts.related_serializer()
        else:
            return self.opts.field_serializer()
    
    def get_object_fields_names(self, obj):
        concrete_model = obj._meta.concrete_model
        names = []
        names.extend([field.name for field in concrete_model._meta.local_fields if field.serialize])
        names.extend([field.name for field in concrete_model._meta.many_to_many if field.serialize])
        return names
    
    def get_deserializable_fields_for_object(self, obj):
        return self.get_fields_for_object(obj.object)

    def _deserialize(self, serialized_obj, instance, field_name):
        # instance is of DeserializedObject type
        if not self.follow_object:
            return self.deserialize(serialized_obj, instance)
        else:
            setattr(instance.object, field_name, self.deserialize(serialized_obj))
            return instance

    def _get_instance(self, obj, instance=None):
        if instance is None:
            return base.DeserializedObject(self.create_instance(obj))
        else:
            return instance
    
    def create_instance(self, serialized_obj):
        if self.opts.class_name is not None:
            if isinstance(self.opts.class_name, str):
                return _get_model(serialized_obj[self.opts.class_name])()
            else:
                return self.opts.class_name()
        raise base.DeserializationError(u"Can't resolve class for object creation")


class ModelSerializer(BaseModelSerializer):
    """
    Class for serializing Django models.

    """
    __metaclass__=ModelSerializerMetaclass


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
