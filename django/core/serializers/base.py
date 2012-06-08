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

    def __init__(self, label=None, follow_object=False, attribute=False):
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
            return obj
        elif hasattr(obj, '__iter__'):
            return self.serialize_iterable(obj)
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
        if isinstance(obj, dict):
            return self.deserialize_object(obj, instance, field_name)
        if hasattr(obj, '__iter__'):
            return self.deserialize_iterable(obj, instance, field_name)
        else:
            return self.deserialize_object(obj, instance, field_name)

    def deserialize_object(self, obj, instance, field_name):
        new_instance = self.create_instance() if self.follow_object else None
        fields = self.get_fields_for_object(new_instance or instance)
        return_instance = self.get_instance_from_native(obj, new_instance or instance, fields)
        if self.follow_object:
            setattr(instance, field_name, return_instance)
        return instance

    def get_instance_from_native(self, obj, instance, fields):
        native, attributes = obj
        for field_name, serializer in fields.iteritems():
            serialized_name = serializer.label if serializer.label is not None else field_name

            if serializer.attribute:
                serializer.deserialize(attributes[serialized_name], instance, field_name)
            else:
                serializer.deserialize(native[serialized_name], instance, field_name)
        return instance

    def create_instance(self, obj, instance, field_name):
        if self.opts.class_name is not None:
            if isinstance(self.opts.class_name, str):
                return object#class_from_string(self.opts.class_name)
            else:
                return self.opts.class_name
        return object


class Serializer(BaseSerializer):
    __metaclass__ = SerializerMetaclass


class Field(Serializer):
    def __init__(self, label=None, follow_object=False, attribute=False):
        if attribute and self.base_fields:
            raise SerializerError("Attribute Field can't have declared fields")
        super(Field, self).__init__(label, follow_object, attribute)

    def serialize(self, obj, field_name):
        native, attributes = super(Serializer, self).serialize(obj, field_name)
        new_name = self.field_name(obj, field_name)
        if new_name is None:
            if not native:  # only __attributes__ key
                return (self.serialized_value(obj, field_name), attributes)
            raise SerializationError("field_name must be present if there are nasted Fields in Field")
        else:
            native[new_name] = self.serialized_value(obj, field_name)
        return (native, attributes)

    def serialized_value(self, obj, field_name):
        return getattr(obj, field_name)

    def field_name(self, obj, field_name):
        return None


    def deserialize(self, obj, instance=None, field_name=None):
        super(Serializer, self).deserialize(obj, instance, field_name)

    def deserialized_value(self, obj, instance, field_name):
        fn = self.field_name(self, instance, field_name)
        val = obj[fn] if fn else obj
        setattr(instance, field_name, val)


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
        self.field_serializer = getattr(options, 'field_serializer', Field)
        self.related_reserialize = getattr(options, 'related_reserialize', None)


class ObjectSerializerMetaclass(SerializerMetaclass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ObjectSerializerMetaclass, cls).__new__(cls, name, bases, attrs)
        new_class._meta = ObjectSerializerOptions(getattr(new_class, 'Meta', None))
        return new_class


class BaseObjectSerializer(Serializer):

    def __init__(self, label=None, attribute=None, follow_object=False, **kwargs):
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


class ObjectSerializer(BaseObjectSerializer):
    __metaclass__ = ObjectSerializerMetaclass


class ModelSerializer(ObjectSerializer):
    pass

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
