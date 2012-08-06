"""
YAML serializer.

Requires PyYaml (http://pyyaml.org/), but that's checked for in __init__.
"""

import decimal
import yaml
import types
from io import StringIO

from django.utils.datastructures import SortedDict

from django.core.serializers import native
from django.core.serializers import base
from django.core.serializers import field
from django.core.serializers.utils import ObjectWithMetadata

class DjangoSafeDumper(yaml.SafeDumper):
    def represent_decimal(self, data):
        return self.represent_scalar('tag:yaml.org,2002:str', str(data))
    def represent_object_with_metadata(self, data):
        return self.represent_data(data.get_object())

DjangoSafeDumper.add_representer(decimal.Decimal, DjangoSafeDumper.represent_decimal)
DjangoSafeDumper.add_representer(ObjectWithMetadata, DjangoSafeDumper.represent_object_with_metadata)
DjangoSafeDumper.add_representer(types.GeneratorType, yaml.representer.SafeRepresenter.represent_list)
DjangoSafeDumper.add_representer(SortedDict, yaml.representer.SafeRepresenter.represent_dict)

class FieldsSerializer(native.ModelSerializer):
    pass


class Serializer(native.ModelSerializer):
    internal_use_only = False
    
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

class NativeFormat(base.NativeFormat):
    def serialize_objects(self, obj):
        yaml.dump(obj, self.stream, Dumper=DjangoSafeDumper, **self.options)

    def deserialize_stream(self, stream_or_string):
        if isinstance(stream_or_string, bytes):
            stream_or_string = stream_or_string.decode('utf-8')
        if isinstance(stream_or_string, basestring):
            stream = StringIO(stream_or_string)
        else:
            stream = stream_or_string
        return yaml.safe_load(stream)

