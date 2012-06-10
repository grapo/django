"""
XML serializer.
"""

from django.core.serializers import base


class Serializer(base.ObjectSerializer):
    internal_use_only=False


class NativeFormat(base.NativeFormat):
    pass
