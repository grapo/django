"""
Serialize data to/from JSON
"""

# Avoid shadowing the standard library json module
from __future__ import absolute_import

import datetime
import decimal
import json
import inspect

from django.utils import six
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
        return (unpack_object(o) for o in obj)
    else:
        return obj


class NativeFormat(base.NativeFormat):
    def serialize_objects(self, obj):
        if json.__version__.split('.') >= ['2', '1', '3']:
            # Use JS strings to represent Python Decimal instances (ticket #16850)
            self.options.update({'use_decimal': False})
        obj = unpack_object(obj)
        json.dump(obj, self.stream, cls=DjangoJSONEncoder, **self.options)

    def deserialize_stream(self, stream_or_string):
        if isinstance(stream_or_string, bytes):
            stream_or_string = stream_or_string.decode('utf-8')
        try: 
            if isinstance(stream_or_string, six.string_types):
                return json.loads(stream_or_string)
            else:
                return json.load(stream_or_string)
        except Exception, e:
            raise base.DeserializationError(e)

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
