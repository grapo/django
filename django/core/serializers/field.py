"""
Module for field serializer/unserializer classes.
"""
from django.core.serializers.base import Serializer
from django.core.serializers.utils import DictWithMetadata
from django.utils.encoding import is_protected_type, smart_unicode

class Field(Serializer):
    """ 
    Class that serialize and deserialize object to python native datatype.
    
    """
    def __init__(self, label=None):
        super(Field, self).__init__(label=label, follow_object=False)

    def _serialize(self, obj, field_name):
        new_obj = self.get_object(obj, field_name)
        serialized_obj = self.serialize(new_obj)
        metadict = self._metadata(obj, field_name)
        return (serialized_obj, metadict)

    def _serialize_fields(self, obj, orig_field_name):
        fields = DictWithMetadata()
        for field_name, serializer in self.base_fields.iteritems():
            nativ_obj, metadict = serializer._serialize(obj, orig_field_name)
            if serializer.label:
                field_name = serializer.label
            fields.set_with_metadata(field_name, nativ_obj, metadict)
        return fields

    def _metadata(self, obj, field_name):
        fields = self._serialize_fields(obj, field_name)
        metadict = {'fields': fields}
        metadict = self.metadata(metadict)
        return metadict

    def get_object(self, obj, field_name):
        """ 
        Returns object that should be serialized.
        """
        return getattr(obj, field_name, obj)

    def serialize(self, obj):
        if isinstance(obj, dict):
            return dict([(k, self.serialize(v)) for k, v in obj.iteritems()])
        elif hasattr(obj, '__iter__'):
            return (self.serialize(o) for o in obj)
        else:
            return self.serialize_value(obj)

    def serialize_value(self, obj):
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
        if isinstance(obj, dict):
            return dict([(k, self.deserialize(v)) for k, v in obj.iteritems()])
        elif hasattr(obj, '__iter__'):
            return (self.deserialize(o) for o in obj)
        else:
            return self.deserialize_value(obj)

    def deserialize_value(self, obj):
        """
        Returns object that will be assign as field to instance
        """
        return obj


class ModelField(Field):
    def get_object(self, obj, field_name):
        field = obj._meta.get_field_by_name(field_name)[0]
        value = field._get_val_from_obj(obj)
        if is_protected_type(value):
            return value
        else:
            return field.value_to_string(obj)

    def serialize(self, obj):
        return obj

    def set_object(self, obj, instance, field_name):
        setattr(instance.object, field_name, obj)

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
    
    def serialize(self, obj):
        if hasattr(obj, '__iter__'):
            return (self.serialize(o) for o in obj)
        elif is_protected_type(obj):
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
