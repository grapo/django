"""
A Python "serializer". Doesn't do much serializing per se -- just converts to
and from basic Python data types (lists, dicts, strings, etc.). Useful as a basis for
other serializers.
"""
#from __future__ import unicode_literals

from django.core.serializers import native
from django.core.serializers import base



class NativeSerializer(native.DumpdataSerializer):
   pass 


class FormatSerializer(base.FormatSerializer):
    def serialize_objects(self, obj):
        self.objects = obj
    
    def getvalue(self):
        return self.objects


class Serializer(base.Serializer):
    internal_use_only = True
    SerializerClass = NativeSerializer
    RendererClass = FormatSerializer


Deserializer = Serializer
