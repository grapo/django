"""
XML serializer.
"""
import StringIO
from xml.etree.ElementTree import iterparse

from django.conf import settings
from django.utils.xmlutils import SimplerXMLGenerator
#from xml.dom import pulldom
from django.utils.encoding import smart_unicode
from django.core.serializers import  native
from django.core.serializers import base
from django.core.serializers import field
from django.core.serializers.utils import IterableWithMetadata, MappingWithMetadata, ObjectWithMetadata

class TypeField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.get_internal_type()

class NameField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.name

class ModelWithAttributes(field.ModelField):
    type = TypeField()
    name = NameField()

    def metadata(self, metadict):
        metadict['attributes'] = ['type', 'name']
        return metadict

class RelField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.rel.__class__.__name__


class ToField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return smart_unicode(field.rel.to._meta)

class RelatedWithAttributes(field.RelatedField):
    name = NameField() 
    rel = RelField()
    to = ToField()

    def metadata(self, metadict):
        metadict['attributes'] = ['name', 'rel', 'to']
        return metadict

class EmptyField(field.Field):
    def serialize(self, obj):
        return {'pk' : obj}

    def metadata(self, metadict):
        metadict['attributes'] = ['pk']
        return metadict

class M2mWithAttributes(field.M2mField):
    name = NameField() 
    rel = RelField()
    to = ToField()

    def serialize_iterable(self, obj):
        rf = EmptyField()
        for o in obj:
            f = rf.serialize(o._get_pk_val()) 
            yield f
    def metadata(self, metadict):
        metadict['attributes'] = ['name', 'rel', 'to']
        return metadict


class FieldsSerializer(native.ModelSerializer):
    def metadata(self, metadict):
        metadict['as_list'] = True
        return metadict

    class Meta:
       field_serializer = ModelWithAttributes
       related_serializer = RelatedWithAttributes
       m2m_serializer = M2mWithAttributes

class Serializer(native.ModelSerializer):
    internal_use_only = False
    
    pk = field.PrimaryKeyField()
    model = field.ModelNameField() 
    field = FieldsSerializer(follow_object=False)


    def __init__(self, label=None, follow_object=True, **kwargs):
        super(Serializer, self).__init__(label, follow_object)
        # should this be rewrited?
        self.base_fields['field'].opts = native.make_options(self.base_fields['field']._meta, **kwargs)
        
    def metadata(self, metadict):
        metadict['attributes'] = ['pk', 'model']
        return metadict

    class Meta:
        fields = ()
        class_name = "model"


class NativeFormat(base.NativeFormat):
    def indent(self, xml, level):
        xml.ignorableWhitespace('\n' + ' ' * 4 * level)
    
    def serialize(self, obj, **options):
        stream = StringIO.StringIO()
        xml = SimplerXMLGenerator(stream, settings.DEFAULT_CHARSET)
        xml.startDocument()
        xml.startElement("django-objects", {"version" : "1.0"})
        level = 0
        self._start_xml(xml, obj, level + 1)
        self.indent(xml, level)
        xml.endElement("django-objects")
        xml.endDocument()
    
        return stream.getvalue()

    def _start_xml(self, xml, data, level, name="object", attributes=None): 
        if isinstance(data, MappingWithMetadata):
            for key, value in data.items():
                elem_name = name if data.metadata.get('as_list', False) else key
                self._to_xml(xml, value, level + 1, elem_name)
        elif isinstance(data, IterableWithMetadata):
            for item in data:
                self._to_xml(xml, item, level)
        else:
            xml.characters(str(data._object))

    def _to_xml(self, xml, data, level, name='object', attributes=None):
        attributes = attributes or {}
        for attr_name  in data.metadata.get('attributes', []):
            if attr_name in data.fields:
                attributes[attr_name] = str(data.fields[attr_name])
            elif isinstance(data, MappingWithMetadata) and attr_name in data:
                attributes[attr_name] = str(data.pop(attr_name))
                
        self.indent(xml, level)
        xml.startElement(name, attributes)
        
        if isinstance(data, MappingWithMetadata):
            for key, value in data.items():
                if value.metadata.get('as_list', False):
                    self._start_xml(xml, value, level, key)
                else:
                    self._to_xml(xml, value, level + 1, key)
            self.indent(xml, level)
        elif isinstance(data, IterableWithMetadata):
            for item in data:
                self._to_xml(xml, item, level + 1)
            self.indent(xml, level)
        else:
            xml.characters(str(data._object))
        
        xml.endElement(name)

    
    def deserialize(self, obj, **options):
        event_stream = iterparse(StringIO.StringIO(obj), events=['start', 'end'])
        while True:
            event, node = event_stream.next() # will raise StopIteration exception.
            if node.tag == 'django-objects':
                continue
            data, node = self._to_python(node, event_stream)
            yield data    

