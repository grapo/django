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
    class Meta:
        pass

    creation_counter = 0

    def __init__(self, label=None, attribute=None):
        self.label = label
        self.attribute = attribute

    def get_object(self, obj, field_name):
        raise NotImplementedError()

    def get_fields_for_object(self, obj):
        raise NotImplementedError()

    def get_serializer_for_field(self, field_name):
        raise NotImplementedError()
        
    def set_fields_serializers(self, fields):
        # each field must have serializer for it
        for f in fields.keys():
            if fields[f] == None:
                fields[f] = self.get_serializer_for_field(f)

    def get_native_from_object(self, obj, fields):
        native = {'__attributes__' : {}}
        for field_name, serializer in fields.iteritems():
            nativ_obj = serializer.serialize(obj, field_name)
            if serializer.label:
                field_name = serializer.label
            
            if serializer.attribute:
                native['__attributes__'][field_name] = nativ_obj
            else:
                native[field_name] = nativ_obj
        return native

    def serialize_iterable(self, obj, **options):
        for item in obj:
            yield self.serialize(item, **options)

    def serialize(self, obj, field_name=None, **options):
        if is_protected_type(obj):
            return obj
        elif hasattr(obj, '__iter__'):
            return self.serialize_iterable(obj, **options)
        else:
            obj = self.get_object(obj, field_name)
            fields = self.get_fields_for_object(obj)
            self.set_fields_serializers(fields)
            return self.get_native_from_object(obj, fields)

            
class Serializer(BaseSerializer): 
    __metaclass__ = SerializerMetaclass


class Field(Serializer): 
    
    def get_object(self, obj, field_name):
        return obj

    def get_fields_for_object(self, obj):
        return self.base_fields

    def serialize(self, obj, field_name):
        native_datatype = super(Serializer, self).serialize(obj, field_name)
        new_name = self.field_name(obj, field_name)
        if new_name is None:
            if len(native_datatype.keys()) < 2: # only __attributes__ key
                return self.serialized_value(obj, field_name) # TODO Bug: if field_name -> None then attributes 
                                                              # are not returned
            raise SerializationError("field_name must be present if there are nasted Fields in Field")
        else:
            native_datatype[new_name] = self.serialized_value(obj, field_name)
        return native_datatype
    
    def serialized_value(self, obj, field_name):
        return getattr(obj, field_name)

    def field_name(self, obj, field_name):
        return None
    

def make_options(options, meta, **kwargs):
    for name in options.__dict__:
        attr = kwargs.get(name, getattr(meta, name, None))
        if attr:
            setattr(options, name, attr)
    return options


class ObjectSerializerOptions(object):
    def __init__(self):
        self.fields = ()
        self.exclude = ()
        self.related_serializer = None
        self.field_serializer = Field
        self.related_reserialize = None
        self.include_default_fields = True
        self.follow_object = True
        self.model_fields = ['pk', 'fields', 'related_fields']


class ObjectSerializer(Serializer):
    _options_class=ObjectSerializerOptions

    def __init__(self, **kwargs):
        super(ObjectSerializer, self).__init__(**kwargs)
        self.opts = make_options(self._options_class(), self.Meta, **kwargs)
    
    def get_serializer_for_field(self, field_name):
        return self.opts.field_serializer()
    
    def get_object(self, obj, field_name):
        if field_name is not None:
            if  self.opts.follow_object and hasattr(obj, field_name):
                return getattr(obj, field_name)
        return obj

    def get_fields_for_object(self, obj):
        fields = {}
        if self.opts.include_default_fields:
            for f in self.get_obj_default_fields(obj):
                if f not in self.opts.exclude:
                    fields.setdefault(f, None)
        fields.update(dict.fromkeys(self.opts.fields))
        fields.update(self.base_fields)
        return fields            

    def get_obj_default_fields(self, obj):
        return obj.__dict__.keys()



class ModelSerializerOptions(ObjectSerializerOptions):
    def __init__(self):
        super(ModelSerializerOptions, self).__init__()
        self.model_fields = ['pk', 'fields', 'related_fields']


class ModelSerializer(ObjectSerializer): 
    _options_class=ModelSerializerOptions
    
    def get_obj_default_fields(self, obj):
        # TODO Take in account self.opts.model_fields types
        return obj.__dict__.keys()


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
