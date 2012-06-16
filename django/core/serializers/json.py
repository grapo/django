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


class Serializer(native.ObjectSerializer):
    internal_use_only=False

def remove_arguments(obj):
    if isinstance(obj, tuple):
        obj = obj[0]

    if base.is_protected_type(obj):
        new_obj = obj
    elif isinstance(obj, dict):
        new_obj = {}
        for k,v in obj.iteritems():
            new_obj[k] = remove_arguments(v)
    elif hasattr(obj, '__iter__'):
        new_obj = []
        for item in obj:
            new_obj.append(remove_arguments(item))
    else:
        new_obj = obj
    return new_obj

class NativeFormat(base.NativeFormat):
    def serialize(self, obj, **options):
        obj = remove_arguments(obj)
        return json.dumps(obj, cls=DjangoJSONEncoder, **options)



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
        elif inspect.isgenerator(o):
            return self.default(list(o))
        else:
            return super(DjangoJSONEncoder, self).default(o)

# Older, deprecated class name (for backwards compatibility purposes).
DateTimeAwareJSONEncoder = DjangoJSONEncoder

