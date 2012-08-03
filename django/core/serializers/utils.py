import collections

class ObjectWithMetadata(object):
    def __init__(self, obj, metadata=None, fields=None):
        self._object = obj
        self.metadata = metadata or {}
        self.fields = fields or {}

    def __repr__(self):
        return "<Meta: " + self._object.__repr__() + ">"
    def __str__(self):
        return self._object.__str__()

    def __unicode__(self):
        return self._object.__unicode__()

    def get_object(self):
        return self._object
    
    def __getattribute__(self, attr):
        if attr not in ['_object', 'metadata', 'fields', 'get_object']:
            return self._object.__getattribute__(attr)
        else:
            return object.__getattribute__(self, attr)

class MappingWithMetadata(ObjectWithMetadata, collections.MutableMapping):
    def __getitem__(self, key):
        return self._object.__getitem__(key)

    def __len__(self):
        return self._object.__len__()

    def __contains__(self, key):
        return self._object.__contains__(key)

    def __iter__(self):
        return self._object.__iter__()

    def __setitem__(self, key, value):
        return self._object.__setitem__(key, value)

    def __delitem__(self, key):
        return self._object.__delitem__(key)


class IterableWithMetadata(ObjectWithMetadata, collections.Iterable):
    def __iter__(self):
        return self._object.__iter__()


