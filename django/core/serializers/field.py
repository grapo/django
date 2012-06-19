"""
Module for field serializer/unserializer classes.
"""
from django.core.serializers import base

class FieldMetaclass(base.SerializerMetaclass):
    """
    Metaclass that converts Serializer attributes to a dictionary called
    'base_fields', taking into account parent class 'base_fields' as well.
    """
    def __new__(cls, name, bases, attrs):
        new_class = super(FieldMetaclass,
                     cls).__new__(cls, name, bases, attrs)
        for field in new_class.base_fields.itervalues():
            if not field.attribute:
                raise base.SerializerError("Field subfields must be attributes")
        return new_class


class BaseField(base.Serializer):
    def __init__(self, label=None, attribute=False):
        if attribute and self.base_fields:
            raise base.SerializerError("Attribute Field can't have declared fields")
        super(BaseField, self).__init__(label, attribute, False)

    def serialize(self, obj, field_name):
        native, attributes = super(BaseField, self).serialize(obj, field_name)
        assert native == {}
        return (self.serialized_value(obj, field_name), attributes) # serialized_value can only return native datatype

    def deserialize(self, obj, instance, field_name):
        native, attributes = obj
        self.deserialized_value(native, instance, field_name)
        native, attributes = obj
        fields = self.get_fields_for_object(instance)
         
        for field_name, serializer in fields.iteritems():
            serialized_name = serializer.label if serializer.label is not None else field_name
            if serializer.attribute and serialized_name in attributes:
                instance = serializer.deserialize(attributes[serialized_name], instance, field_name)

        return instance

    def serialized_value(self, obj, field_name):
        return getattr(obj, field_name)

    def deserialized_value(self, obj, instance, field_name):
        setattr(instance, field_name, obj)


class Field(BaseField):
    __metaclass__ = FieldMetaclass

