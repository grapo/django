class DictWithMetadata(dict):
    """
    A dict-like object, that can have additional metadata attached.
    """
    def __init__(self, *args, **kwargs):
        super(DictWithMetadata, self).__init__(*args, **kwargs)
        self.metadata = {}

    def set_with_metadata(self, key, value, metadata):
        self[key] = value
        self.metadata[key] = metadata

    def items_with_metadata(self):
        return [(key, value, self.metadata[key])
        for (key, value) in self.items()]
