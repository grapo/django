"""
Serialize data to/from JSON
"""

# Avoid shadowing the standard library json module
from __future__ import absolute_import

import datetime
import decimal
import json
import inspect

from django.utils.timezone import is_aware
from django.core.serializers import native
from django.core.serializers import base
from django.core.serializers import field
from django.core.serializers.utils import ObjectWithMetadata



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
    def serialize(self, obj, **options):
        options.pop('stream', None)
        options.pop('fields', None)
        return json.dumps(obj, cls=DjangoJSONEncoder, **options)

    def deserialize(self, obj, **options):
        return json.loads(obj, **options)


class DjangoJSONEncoder(json.JSONEncoder):
    """
    JSONEncoder subclass that knows how to encode date/time and decimal types.
    """
    def default(self, o):
        # See "Date Time String Format" in the ECMA-262 specification.
        if isinstance(o, datetime.datetime):
            r = o.isoformat()
            if o.microsecond:
                r = r[:23] + r[26:]
            if r.endswith('+00:00'):
                r = r[:-6] + 'Z'
            return r
        elif isinstance(o, datetime.date):
            return o.isoformat()
        elif isinstance(o, datetime.time):
            if is_aware(o):
                raise ValueError("JSON can't represent timezone-aware times.")
            r = o.isoformat()
            if o.microsecond:
                r = r[:12]
            return r
        elif isinstance(o, decimal.Decimal):
            return str(o)
        elif isinstance(o, ObjectWithMetadata):
            return o.get_object() 
        elif inspect.isgenerator(o):
            return list(o)
        else:
            return super(DjangoJSONEncoder, self).default(o)

# Older, deprecated class name (for backwards compatibility purposes).
DateTimeAwareJSONEncoder = DjangoJSONEncoder
