"""
A Python "serializer". Doesn't do much serializing per se -- just converts to
and from basic Python data types (lists, dicts, strings, etc.). Useful as a basis for
other serializers.
"""

from django.core.serializers import base


class Serializer(base.ObjectSerializer):
    internal_use_only = True


class NativeFormat(base.NativeFormat):
    pass
