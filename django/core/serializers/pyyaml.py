"""
YAML serializer.

Requires PyYaml (http://pyyaml.org/), but that's checked for in __init__.
"""

import decimal
import yaml
import types
from io import StringIO
import datetime

from django.utils.datastructures import SortedDict
from django.utils import six

from django.core.serializers import native
from django.core.serializers import base
from django.core.serializers import field
from django.core.serializers.utils import ObjectWithMetadata


class DjangoSafeDumper(yaml.SafeDumper):
    def represent_decimal(self, data):
        return self.represent_scalar('tag:yaml.org,2002:str', str(data))

    def represent_time(self, data):
        return self.represent_data(str(data))

    def represent_object_with_metadata(self, data):
        return self.represent_data(data.get_object())


DjangoSafeDumper.add_representer(datetime.time, DjangoSafeDumper.represent_time)
DjangoSafeDumper.add_representer(decimal.Decimal, DjangoSafeDumper.represent_decimal)
DjangoSafeDumper.add_representer(ObjectWithMetadata, DjangoSafeDumper.represent_object_with_metadata)
DjangoSafeDumper.add_representer(types.GeneratorType, yaml.representer.SafeRepresenter.represent_list)
DjangoSafeDumper.add_representer(SortedDict, yaml.representer.SafeRepresenter.represent_dict)


class NativeSerializer(native.DumpdataSerializer):
    pass


class FormatSerializer(base.FormatSerializer):
    def serialize_objects(self, obj):
        yaml.dump(obj, self.stream, Dumper=DjangoSafeDumper, **self.options)

    def deserialize_stream(self, stream_or_string):
        if isinstance(stream_or_string, bytes):
            stream_or_string = stream_or_string.decode('utf-8')
        if isinstance(stream_or_string, six.string_types):
            stream = StringIO(stream_or_string)
        else:
            stream = stream_or_string
        try:
            return yaml.safe_load(stream)
        except Exception, e:
            raise base.DeserializationError(e)


class Serializer(base.Serializer):
    SerializerClass = NativeSerializer
    RendererClass = FormatSerializer


Deserializer = Serializer
