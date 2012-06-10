"""
Module for abstract serializer/unserializer base classes.
"""
import datetime
from decimal import Decimal

from django.utils.datastructures import SortedDict
from django.db import models

def is_protected_type(obj):
    """Determine if the object instance is of a protected type.

    Objects of protected types are preserved as-is when passed to
    Serializer.serialize method.
    """
    return isinstance(obj, (
        type(None),
        int, long,
        datetime.datetime, datetime.date, datetime.time,
        float, Decimal,
        basestring)
    )


class SerializerDoesNotExist(KeyError):
    """The requested serializer was not found."""
    pass


class SerializerError(Exception):
    """Something bad happened during Serializer initialization."""
    pass


class SerializationError(Exception):
    """Something bad happened during serialization."""
    pass


class DeserializationError(Exception):
    """Something bad happened during deserialization."""
    pass


def get_declared_fields(bases, attrs):
    """
    Create a list of serializer field instances from the passed in 'attrs', plus any
    similar fields on the base classes (in 'bases').
    """
    fields = [(field_name, attrs.pop(field_name)) for field_name, obj in attrs.items() if isinstance(obj, BaseSerializer)]
    fields.sort(key=lambda x: x[1].creation_counter)

    # If this class is subclassing another Serializer, add that Serializer's fields.
    # Note that we loop over the bases in *reverse*. This is necessary in
    # order to preserve the correct order of fields.
    for base in bases[::-1]:
        if hasattr(base, 'base_fields'):
            fields = base.base_fields.items() + fields

    return SortedDict(fields)


class SerializerMetaclass(type):
    """
    Metaclass that converts Serializer attributes to a dictionary called
    'base_fields', taking into account parent class 'base_fields' as well.
    """
    def __new__(cls, name, bases, attrs):
        attrs['base_fields'] = get_declared_fields(bases, attrs)
        return super(SerializerMetaclass,
                     cls).__new__(cls, name, bases, attrs)


class BaseSerializer(object):
    creation_counter = 0

    def __init__(self, label=None, follow_object=True, attribute=False):
        self.label = label
        self.follow_object = follow_object
        self.attribute = attribute

    def get_object(self, obj, field_name):
        if self.follow_object:
            return getattr(obj, field_name)
        return obj

    def get_fields_for_object(self, obj):
        return self.base_fields

    def get_native_from_object(self, obj, fields):
        native = {}
        attributes = {}
        for field_name, serializer in fields.iteritems():
            nativ_obj = serializer.serialize(obj, field_name)
            if serializer.label:
                field_name = serializer.label

            if serializer.attribute:
                attributes[field_name] = nativ_obj
            else:
                native[field_name] = nativ_obj
        return (native, attributes)

    def serialize_iterable(self, obj):
        for item in obj:
            yield self.serialize(item)

    def serialize(self, obj, field_name=None):
        if is_protected_type(obj):
            return (obj, {})
        elif isinstance(obj, dict):
            return (dict([(k, self.serialize_object(v, field_name)) for k,v in obj.items()] ), {})
        elif hasattr(obj, '__iter__'):
            return (self.serialize_iterable(obj), {})
        else:
            return self.serialize_object(obj, field_name)

    def serialize_object(self, obj, field_name):
        obj = self.get_object(obj, field_name)
        fields = self.get_fields_for_object(obj)
        return self.get_native_from_object(obj, fields)

    def deserialize_iterable(self, obj, instance, field_name):
        for item in obj:
            yield self.deserialize(item, instance, field_name)

    def deserialize(self, obj, instance=None, field_name=None):
        native, attributes = obj
        if not isinstance(native, dict) and hasattr(native, '__iter__'):
            if instance is None:
                return self.deserialize_iterable(native, instance, field_name)
            else:
                setattr(instance, field_name, self.deserialize_iterable(native, instance, field_name))
                return instance

        join_dict = dict(native.items() + attributes.items()) # keys in native are always diffrent than in attributes
        
        new_instance = self.get_instance(join_dict, instance) # possibly new_instance == instance
        fields = self.get_fields_for_object(new_instance)
        for field_name, serializer in fields.iteritems():
            serialized_name = serializer.label if serializer.label is not None else field_name
            if serializer.attribute:
                new_instance = serializer.deserialize(attributes[serialized_name], new_instance, field_name)
            else:
                new_instance = serializer.deserialize(native[serialized_name], new_instance, field_name)
        return new_instance

    def get_instance(self, obj, instance):
        if instance is None:
            new_instance = self.create_instance(obj)
        elif self.follow_object:
            new_instance = self.create_instance(obj)
        else:
            new_instance = instance

        return new_instance

    def create_instance(self, obj):
        raise NotImplementedError()


class Serializer(BaseSerializer):
    __metaclass__ = SerializerMetaclass


class DeserializedObject(object):
    """
    A deserialized model.

    Basically a container for holding the pre-saved deserialized data along
    with the many-to-many data saved with the object.

    Call ``save()`` to save the object (with the many-to-many data) to the
    database; call ``save(save_m2m=False)`` to save just the object fields
    (and not touch the many-to-many stuff.)
    """

    def __init__(self, obj, m2m_data=None):
        self.object = obj
        self.m2m_data = m2m_data

    def __repr__(self):
        return "<DeserializedObject: %s.%s(pk=%s)>" % (
            self.object._meta.app_label, self.object._meta.object_name, self.object.pk)

    def save(self, save_m2m=True, using=None):
        # Call save on the Model baseclass directly. This bypasses any
        # model-defined save. The save is also forced to be raw.
        # This ensures that the data that is deserialized is literally
        # what came from the file, not post-processed by pre_save/save
        # methods.
        models.Model.save_base(self.object, using=using, raw=True)
        if self.m2m_data and save_m2m:
            for accessor_name, object_list in self.m2m_data.items():
                setattr(self.object, accessor_name, object_list)

        # prevent a second (possibly accidental) call to save() from saving
        # the m2m data twice.
        self.m2m_data = None


def _get_model(model_identifier):
    """
    Helper to look up a model from an "app_label.module_name" string.
    """
    try:
        Model = models.get_model(*model_identifier.split("."))
    except TypeError:
        Model = None
    if Model is None:
        raise DeserializationError(u"Invalid model identifier: '%s'" % model_identifier)
    return Model
