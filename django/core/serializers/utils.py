import collections

class ObjectWithMetadata(object):
    def __init__(self, obj, metadata=None, fields=None):
        self._object = obj
        self.metadata = None
        self.fields = None

    def __repr__(self):
        return self._object.__repr__()
    def __str__(self):
        return self._object.__str__()

    def __unicode__(self):
        return self._object.__unicode__()

    def get_object(self):
        return self._object

class MappingWithMetadata(ObjectWithMetadata, collections.Mapping):
    def __getitem__(self, key):
        return self._object.__getitem__(key)

    def __len__(self):
        return self._object.__len__()

    def __contains__(self, key):
        return self._object.__contains__(key)

    def __iter__(self):
        return self._object.__iter__()


class IterableWithMetadata(ObjectWithMetadata, collections.Iterable):
    def __iter__(self):
        return self._object.__iter__()


