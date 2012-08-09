"""
A Python "serializer". Doesn't do much serializing per se -- just converts to
and from basic Python data types (lists, dicts, strings, etc.). Useful as a basis for
other serializers.
"""
#from __future__ import unicode_literals

from django.core.serializers import native
from django.core.serializers import base
from django.core.serializers import field


class FieldsSerializer(native.ModelSerializer):
    pass


class Serializer(native.ModelSerializer):
    internal_use_only = True
    
    pk = field.PrimaryKeyField()
    model = field.ModelNameField() 
    fields = FieldsSerializer(follow_object=False)

    def __init__(self, label=None, follow_object=True, **kwargs):
        super(Serializer, self).__init__(label, follow_object)
        # should this be rewrited?
        self.base_fields['fields'].opts = native.make_options(self.base_fields['fields']._meta, **kwargs)
        
    class Meta:
        fields = ()
        class_name = "model"


def unpack_object(obj):
    if hasattr(obj, 'get_object'):
        obj = obj.get_object()
    else:
        return obj
    if isinstance(obj, dict):
        for key in obj.keys():
            obj[key] = unpack_object(obj[key])
        return obj
    elif hasattr(obj, '__iter__'):
        return [unpack_object(o) for o in obj]
    else:
        return obj


class NativeFormat(base.NativeFormat):
    def serialize_objects(self, obj):
        self.objects =  unpack_object(obj)
    
    def getvalue(self):
        return self.objects

    def deserialize_stream(self, stream_or_string):
        return stream_or_string
