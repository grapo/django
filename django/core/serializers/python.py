"""
A Python "serializer". Doesn't do much serializing per se -- just converts to
and from basic Python data types (lists, dicts, strings, etc.). Useful as a basis for
other serializers.
"""
#from __future__ import unicode_literals

from django.core.serializers import native
from django.core.serializers import base



class Serializer(native.DumpdataSerializer):
    internal_use_only = True


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
