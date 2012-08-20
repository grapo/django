"""
Module for field serializer/unserializer classes.
"""

import collections

from django.utils.datastructures import SortedDict
from django.utils.encoding import is_protected_type, smart_unicode

from django.core.serializers import base
from django.core.serializers.utils import ObjectWithMetadata


class Field(base.NativeSerializer):
    """
    Class that serialize and deserialize object to python native datatype.
    """
    def __init__(self, label=None, **kwargs):
        super(Field, self).__init__(label=label, follow_object=False, **kwargs)

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
        fields = None
        if hasattr(self, 'original_obj') and self.original_field_name:
            fields = self._serialize_fields(self.original_obj, self.original_field_name)
        if not isinstance(obj, collections.Mapping) and hasattr(obj, '__iter__'):
            serialized_obj = self.serialize_iterable(obj)
        else:
            serialized_obj = self.serialize_object(obj)

        if self.context.use_metadata:
            return ObjectWithMetadata(serialized_obj, self.get_metadata(), fields)
        else:
            return serialized_obj

    def serialize_object(self, obj):
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

    def deserialize(self, serialized_obj):
        if not isinstance(serialized_obj, collections.Mapping) and hasattr(serialized_obj, '__iter__'):
            return self.deserialize_iterable(serialized_obj)
        else:
            return self.deserialize_object(serialized_obj)

    def deserialize_object(self, obj):
        """
        Returns object that will be assign as field to instance
        """
        return obj


class ModelField(Field):
    """
    Class for native serialization and deserialization Django model's fields.
    """
    def get_object(self, obj, field_name):
        field = obj._meta.get_field_by_name(field_name)[0]
        value = field._get_val_from_obj(obj)
        if self.context.text_only:
            if value is None:
                return value
        else:
            if is_protected_type(value):
                return value

        return field.value_to_string(obj)

    def _deserialize(self, serialized_obj, instance, field_name):
        field = instance.ModelClass._meta.get_field(field_name)
        self.set_object(self.deserialize(serialized_obj, field), instance, field_name)
        return instance

    def deserialize(self, serialized_obj, field):
        if not isinstance(serialized_obj, collections.Mapping) and hasattr(serialized_obj, '__iter__'):
            return self.deserialize_iterable(serialized_obj, field)
        else:
            return self.deserialize_object(serialized_obj, field)

    def deserialize_iterable(self, obj, field):
        for o in obj:
            yield self.deserialize(o, field)

    def deserialize_object(self, obj, field):
        if isinstance(obj, str):
            obj = smart_unicode(obj, self.context.encoding, strings_only=True)
        return field.to_python(obj)

    def set_object(self, obj, instance, field_name):
        instance.instance_dict[field_name] = obj


class RelatedField(ModelField):
    """
    Class for native serialization and deserialization Django model's related fields.
    """
    def get_object(self, obj, field_name):
        field = obj._meta.get_field(field_name)
        if self.context.use_natural_keys and hasattr(field.rel.to, 'natural_key'):
            related = getattr(obj, field.name)
            if related:
                value = related.natural_key()
            else:
                value = None
            return value
        else:
            value = getattr(obj, field.get_attname())

        if self.context.text_only:
            if value is not None:
                return smart_unicode(value)

        return value

    def set_object(self, obj, instance, field_name):
        field = instance.ModelClass._meta.get_field(field_name)
        instance.instance_dict[field.attname] = obj

    def serialize_itarable(self, obj):
        return obj

    def deserialize_iterable(self, obj, field):  # list of natural keys
        return self.deserialize_object(obj, field)

    def deserialize_object(self, obj, field):
        if isinstance(obj, str):
            obj = smart_unicode(obj, self.context.encoding, strings_only=True)
        if hasattr(field.rel.to._default_manager, 'get_by_natural_key'):
            if hasattr(obj, '__iter__'):
                obj = field.rel.to._default_manager.db_manager(self.context.using).get_by_natural_key(*obj)
                value = getattr(obj, field.rel.field_name)
                # If this is a natural foreign key to an object that
                # has a FK/O2O as the foreign key, use the FK value
                if field.rel.to._meta.pk.rel:
                    value = value.pk
            else:
                value = field.rel.to._meta.get_field(field.rel.field_name).to_python(obj)
        else:
            value = field.rel.to._meta.get_field(field.rel.field_name).to_python(obj)
        return value

    def get_metadata(self):
        metadict = super(RelatedField, self).get_metadata()
        metadict['item-name'] = 'natural'
        return metadict


class M2mRelatedField(RelatedField):
    """
    Class for native serialization and deserialization objects in Django model's  m2m fields.
    """

    def serialize_object(self, obj):  # get_object from RelatedField won't be called
        if self.context.use_natural_keys and hasattr(obj, 'natural_key'):
            return obj.natural_key()
        return obj._get_pk_val()

    def deserialize_iterable(self, obj, field):  # list of natural keys
        return self.deserialize_object(obj, field)

    def deserialize_object(self, obj, field):
        if isinstance(obj, str):
            obj = smart_unicode(obj, self.context.encoding, strings_only=True)

        if hasattr(field.rel.to._default_manager, 'get_by_natural_key'):
            if hasattr(obj, '__iter__'):
                return field.rel.to._default_manager.db_manager(self.context.using).get_by_natural_key(*obj).pk
            else:
                return smart_unicode(field.rel.to._meta.pk.to_python(obj))
        else:
            return smart_unicode(field.rel.to._meta.pk.to_python(obj))

    def get_metadata(self):
        metadict = super(M2mRelatedField, self).get_metadata()
        metadict['item-name'] = 'natural'
        return metadict


class M2mField(RelatedField):
    """
    Class for native serialization and deserialization Django model's m2m fields.
    """
    def __init__(self, label=None, related_field=M2mRelatedField, **kwargs):
        self.related_field = related_field()
        super(M2mField, self).__init__(label=label, **kwargs)

    def update_context(self, context):
        super(M2mField, self).update_context(context)
        self.related_field.update_context(context)

    def get_object(self, obj, field_name):
        field, _, _, m2m = obj._meta.get_field_by_name(field_name)
        if m2m and field.rel.through._meta.auto_created:
            return getattr(obj, field_name).iterator()
        raise base.SerializationError(self.__class__.__name__ + " is only for auto created ManyToMany fields serialization")

    def serialize_iterable(self, obj):
        rf = self.related_field

        for o in obj:
            yield rf.serialize(o)

    def deserialize_iterable(self, obj, field):
        rf = self.related_field
        if not isinstance(rf, Field):
            field = None
        for o in obj:
            yield rf.deserialize(o, field)

    def set_object(self, obj, instance, field_name):
        instance.m2m_data[field_name] = obj

    def get_metadata(self):
        metadict = super(RelatedField, self).get_metadata()
        metadict['item-name'] = 'object'
        return metadict


class PrimaryKeyField(ModelField):
    """
    Class for serializaton and deserialization Django model's primary key
    """
    def get_object(self, obj, field_name):
        return obj._get_pk_val()

    def _deserialize(self, serialized_obj, instance, field_name):
        field = instance.ModelClass._meta.pk
        self.set_object(self.deserialize(serialized_obj, field), instance, field.attname)
        return instance


class ModelNameField(Field):
    """
    Serializes the model instance's model name.  Eg. 'auth.User'.
    """
    def get_object(self, obj, field_name):
        return smart_unicode(obj._meta)
