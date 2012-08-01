"""
Module for field serializer/unserializer classes.
"""

import collections
from django.core.serializers import base
from django.utils.datastructures import SortedDict
from django.utils.encoding import is_protected_type, smart_unicode

from django.core.serializers.utils import ObjectWithMetadata, MappingWithMetadata, IterableWithMetadata

class FieldMetaclass(base.SerializerMetaclass):
    @classmethod
    def create_serialize_method(cls, old_serialize, serialize_iterable):
        def serialize(self, obj):
            fields = None
            if hasattr(self, 'original_obj') and self.original_field_name:
                fields = self._serialize_fields(self.original_obj, self.original_field_name)
            if not isinstance(obj, collections.Mapping) and hasattr(obj, '__iter__'):
                serialized_obj = serialize_iterable(self, obj)
            else:
                serialized_obj = old_serialize(self, obj)
            if isinstance(serialized_obj, collections.Mapping):
                return MappingWithMetadata(serialized_obj, self.get_metadata(), fields)
            elif hasattr(serialized_obj, '__iter__'):
                return IterableWithMetadata(serialized_obj, self.get_metadata(), fields)
            else:
                return ObjectWithMetadata(serialized_obj, self.get_metadata(), fields)

        return serialize

    @classmethod
    def create_deserialize_method(cls, old_deserialize, deserialize_iterable):
        def deserialize(self, serialized_obj):
            if not isinstance(serialized_obj, collections.Mapping) and hasattr(serialized_obj, '__iter__'):
                return deserialize_iterable(self, serialized_obj)
            else:
                return old_deserialize(self, serialized_obj)
        
        return deserialize

class BaseField(base.BaseSerializer):
    """ 
    Class that serialize and deserialize object to python native datatype. 
    """
    def __init__(self, label=None):
        super(BaseField, self).__init__(label=label, follow_object=False)

    def _serialize(self, obj, field_name):
        self.original_obj = obj
        self.original_field_name = field_name
        new_obj = self.get_object(obj, field_name)
        serialized_obj = self.serialize(new_obj)
        self.original_obj = None
        self.original_field_name = None
        return serialized_obj

    def _serialize_fields(self, obj, orig_field_name):
        fields = SortedDict()
        for field_name, serializer in self.base_fields.iteritems():
            nativ_obj = serializer._serialize(obj, orig_field_name)
            if serializer.label:
                field_name = serializer.label
            fields[field_name] = nativ_obj
        return fields

    def get_object(self, obj, field_name):
        """ 
        Returns object that should be serialized.
        """
        return getattr(obj, field_name, obj)

    def serialize(self, obj):
        """
        Returns native python datatype.
        
        Object returned by this method must be accepted by serialization
        format or exception will be thrown.
        """
        return obj

    def _deserialize(self, serialized_obj, instance, field_name):
        self.set_object(self.deserialize(serialized_obj), instance, field_name)
        return instance

    def set_object(self, obj, instance, field_name):
        """
        Assigns deserialized object obj to given instance.
        
        If field shouldn't be deserialized then this method
        must be override and do nothing.
        """
        setattr(instance, field_name, obj)

    
    def deserialize(self, obj):
        """
        Returns object that will be assign as field to instance
        """
        return obj

class Field(BaseField):
    __metaclass__ = FieldMetaclass


class ModelField(Field):
    def get_object(self, obj, field_name):
        field = obj._meta.get_field_by_name(field_name)[0]
        value = field._get_val_from_obj(obj)
        if is_protected_type(value):
            return value
        else:
            return field.value_to_string(obj)

    def set_object(self, obj, instance, field_name):
        setattr(instance.object, field_name, obj)

class M2mField(Field):
    def get_object(self, obj, field_name):
        field, _, _, m2m = obj._meta.get_field_by_name(field_name)
        if m2m and field.rel.through._meta.auto_created:
            return getattr(obj, field_name).iterator()
        return field._get_val_from_obj(obj)
    
    def serialize_iterable(self, obj):
        rf = RelatedField()
        for o in obj:
            yield rf.serialize(o._get_pk_val()) 


class RelatedField(Field):
    def get_object(self, obj, field_name):
        field, _, _, m2m = obj._meta.get_field_by_name(field_name)
        if m2m and field.rel.through._meta.auto_created:
            return (o._get_pk_val() for o in getattr(obj, field_name).iterator())
        return field._get_val_from_obj(obj)

    def set_object(self, obj, instance, field_name):
        field, _, _, m2m = instance.object._meta.get_field_by_name(field_name)
        if m2m:
            instance.m2m_data[field_name] = obj
        else:
            setattr(instance.object, field.attname, obj)
    
    def serialize_itarable(self, obj):
        for o in obj:
            yield self.serialize(o)

    def serialize(self, obj):
        if is_protected_type(obj):
            return obj
        else:
            return smart_unicode(obj)


class PrimaryKeyField(ModelField):
    def get_object(self, obj, field_name):
        return obj._get_pk_val()


class ModelNameField(Field):
    """
    Serializes the model instance's model name.  Eg. 'auth.User'.
    """
    def get_object(self, obj, field_name):
        return smart_unicode(obj._meta)
