"""
XML serializer.
"""

from django.core.serializers import  native
from django.core.serializers import base


class Serializer(native.ObjectSerializer):
    internal_use_only=False


class NativeFormat(base.NativeFormat):
    pass
