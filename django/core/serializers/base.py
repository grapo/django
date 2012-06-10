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


class FieldMetaclass(SerializerMetaclass):
    """
    Metaclass that converts Serializer attributes to a dictionary called
    'base_fields', taking into account parent class 'base_fields' as well.
    """
    def __new__(cls, name, bases, attrs):
        new_class = super(FieldMetaclass,
                     cls).__new__(cls, name, bases, attrs)
        for field in new_class.base_fields.itervalues():
            if not field.attribute:
                raise SerializerError("Field subfields must be attributes")
        return new_class


class BaseField(Serializer):
    def __init__(self, label=None, attribute=False):
        if attribute and self.base_fields:
            raise SerializerError("Attribute Field can't have declared fields")
        super(BaseField, self).__init__(label, False, attribute)

    def serialize(self, obj, field_name):
        native, attributes = super(Serializer, self).serialize(obj, field_name)
        assert native == {}
        return (self.serialized_value(obj, field_name), attributes) # serialized_value can only return native datatype

    def deserialize(self, obj, instance, field_name):
        native, attributes = obj
        self.deserialized_value(native, instance, field_name)
        native, attributes = obj
        fields = self.get_fields_for_object(instance)
         
        for field_name, serializer in fields.iteritems():
            serialized_name = serializer.label if serializer.label is not None else field_name
            if serializer.attribute:
                instance = serializer.deserialize(attributes[serialized_name], instance, field_name)

        return instance

    def serialized_value(self, obj, field_name):
        return getattr(obj, field_name)

    def deserialized_value(self, obj, instance, field_name):
        setattr(instance, field_name, obj)


class Field(BaseField):
    __metaclass__ = FieldMetaclass


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
        self.class_name = getattr(options, 'class_name', object)


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
    
    def create_instance(self, obj):
        if self.opts.class_name is not None:
            if isinstance(self.opts.class_name, str):
                return _get_model(obj[self.opts.class_name])()
            else:
                return self.opts.class_name()
        raise DeserializationError(u"Can't resolve model")


class ObjectSerializer(BaseObjectSerializer):
    __metaclass__ = ObjectSerializerMetaclass


class ModelSerializer(ObjectSerializer):
    pass


class NativeFormat(object):
    def serialize(self, objects, **options):
        return objects

    def deserialize(self, stream, **options):
        return stream


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
