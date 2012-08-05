"""
Module for abstract serializer/unserializer base classes.
"""
import collections
import datetime
from io import BytesIO
from decimal import Decimal

from django.utils.datastructures import SortedDict
from django.db import models
from django.core.serializers.utils import ObjectWithMetadata


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
    fields = [(field_name, attrs.pop(field_name)) for field_name, obj in attrs.items() if isinstance(obj, (BaseSerializer))]
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
        new_class = super(SerializerMetaclass,
                     cls).__new__(cls, name, bases, attrs)
       
        return new_class

class BaseSerializer(object):
    creation_counter = 0

    def __init__(self, label=None, follow_object=True):
        self.label = label
        self.follow_object = follow_object
        
        # Increase the creation counter, and save our local copy.
        self.creation_counter = BaseSerializer.creation_counter
        BaseSerializer.creation_counter += 1

    def get_object(self, obj, field_name=None):
        """
        Returns object that should be serialized.
        """
        if self.follow_object and field_name:
            return getattr(obj, field_name)
        return obj

    def get_fields_for_object(self, obj):
        """
        Returns fields that should be serialized in given object.

        Subclasses may wish to override it to handle additional fields,
        not only declared in Serialier.
        """
        return self.base_fields

    def get_metadata(self):
        metadict = {}
        metadict = self.metadata(metadict)
        return metadict

    def metadata(self, metadict):
        """
        Add user defined values to metadict
        """
        return metadict

    def _serialize(self, obj, field_name):
        new_obj = self.get_object(obj, field_name)
        return  self.serialize(new_obj)

    def serialize_iterable(self, obj):
        for o in obj:
            yield self.serialize(o) 

    def serialize(self, obj):
        if not isinstance(obj, collections.Mapping) and hasattr(obj, '__iter__'):
            serialized_obj = self.serialize_iterable(obj)
        else:
            serialized_obj = self.serialize_object(obj)
        
        return ObjectWithMetadata(serialized_obj, self.get_metadata())
    
    def serialize_object(self, obj):
        """
        Serializes given object.
        """
        fields = self.get_fields_for_object(obj)

        native = SortedDict()
        for field_name, serializer in fields.iteritems():
            nativ_obj = serializer._serialize(obj, field_name)
            if serializer.label:
                field_name = serializer.label
            native[field_name] = nativ_obj
        return native

    def get_deserializable_fields_for_object(self, obj): # ugly - how to fix this?
        return self.get_fields_for_object(obj)

    
    def deserialize(self, serialized_obj, instance=None):
        if not isinstance(serialized_obj, collections.Mapping) and hasattr(serialized_obj, '__iter__'):
            return self.deserialize_iterable(serialized_obj)
        else:
            instance = self._get_instance(serialized_obj, instance)
            return self.deserialize_object(serialized_obj, instance)
    
    def deserialize_iterable(self, obj):
        for o in obj:
            yield self.deserialize(o) 
    
    def deserialize_object(self, serialized_obj, instance):
        """
        Deserializes object from give python native datatype.
        """
        fields = self.get_deserializable_fields_for_object(instance)

        for subfield_name, serializer in fields.iteritems():
            serialized_name = serializer.label if serializer.label is not None else subfield_name
            if serialized_name in serialized_obj:
                instance = serializer._deserialize(serialized_obj[serialized_name], instance, subfield_name)
        return instance

    def _deserialize(self, serialized_obj, instance, field_name):
        if not self.follow_object:
            return self.deserialize(serialized_obj, instance)
        else:
            setattr(instance, field_name, self.deserialize(serialized_obj))
            return instance

    def _get_instance(self, obj, instance=None):
        if instance is None:
            return self.create_instance(obj)
        else:
            return instance

    def create_instance(self, serialized_obj):
        """
        Returns instance to which serialized_obj should be deserialized.
        """
        raise NotImplementedError()


class Serializer(BaseSerializer):
    __metaclass__ = SerializerMetaclass


class NativeFormat(object):
    def serialize(self, objects, **options):
        self.stream = options.pop("stream", BytesIO())
        options.pop('fields', None)
        self.options = options
        self.serialize_objects(objects)
        return self.getvalue()

    def getvalue(self):
        """
        Return the fully serialized queryset (or None if the output stream is
        not seekable).
        """
        if callable(getattr(self.stream, 'getvalue', None)):
            return self.stream.getvalue()
    
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
        if m2m_data == None:
            m2m_data = {} # possible backward incompatibility
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
