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

class TypeField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.get_internal_type()


class UnicodeField(field.Field):
    def serialize_object(self, obj):
        return smart_unicode(obj)

class ModelWithAttributes(field.ModelField):
    type = TypeField()

    def metadata(self, metadict):
        metadict['attributes'] = ['type']
        return metadict

    def get_object(self, obj, field_name):
        field = obj._meta.get_field_by_name(field_name)[0]
        return field.value_to_string(obj)


class RelField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.rel.__class__.__name__


class ToField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return smart_unicode(field.rel.to._meta)


class RelatedWithAttributes(field.RelatedField):
    rel = RelField()
    to = ToField()

    def metadata(self, metadict):
        metadict['attributes'] = ['rel', 'to']
        return metadict

    def serialize_object(self, obj):
        return smart_unicode(obj)

class M2mWithAttributes(field.M2mField):
    rel = RelField()
    to = ToField()

    def metadata(self, metadict):
        metadict['attributes'] = ['rel', 'to']
        return metadict

    def serialize_iterable(self, obj):
        serializer = UnicodeField()
        for o in obj:
            yield serializer.serialize(o._get_pk_val()) 


class FieldsSerializer(native.ModelSerializer):
    class Meta:
       field_serializer = ModelWithAttributes
       related_serializer = RelatedWithAttributes
       m2m_serializer = M2mWithAttributes


class Serializer(native.ModelSerializer):
    internal_use_only = False
    
    pk = field.PrimaryKeyField()
    model = field.ModelNameField() 
    fields = FieldsSerializer(follow_object=False)

    def __init__(self, label=None, follow_object=True, **kwargs):
        super(Serializer, self).__init__(label, follow_object)
        # should this be rewrited?
        self.base_fields['fields'].opts = native.make_options(self.base_fields['fields']._meta, **kwargs)

    def metadata(self, metadict):
        metadict['attributes'] = ['pk', 'model']
        return metadict

    class Meta:
        fields = ()
        class_name = "model"


class NativeFormat(base.NativeFormat):
    def indent(self, xml, level):
        xml.ignorableWhitespace('\n' + ' ' * 4 * level)
    
    def serialize_objects(self, obj):
        xml = SimplerXMLGenerator(self.stream, settings.DEFAULT_CHARSET)
        xml.startDocument()
        xml.startElement("django-objects", {"version" : "1.0"})
        level = 0
        self._to_xml(xml, obj, level + 1)
        self.indent(xml, level)
        xml.endElement("django-objects")
        xml.endDocument()
    
    def handle_dict(self, xml, data, level, name="object"):
        add_level = 0
        if name is not None:
            add_level = 1
            attributes = {}
            for attr_name  in data.metadata.get('attributes', []):
                if attr_name in data:
                    attrib = data.pop(attr_name)
                    if attrib._object is not None:
                        attributes[attr_name] = smart_unicode(attrib)
                    
            self.indent(xml, level)
            xml.startElement(name, attributes)
        
        for key, value in data.items():
            self._to_xml(xml, value, level + add_level, key)
        
        if name is not None:
            self.indent(xml, level)
            xml.endElement(name)

    def handle_field(self, xml, data, level, name=None):
        if name is not None:
            attributes = {}
            for attr_name  in data.metadata.get('attributes', []):
                if attr_name in data.fields:
                    attrib = data.fields[attr_name]
                    if attrib is not None:
                        attributes[attr_name] = smart_unicode(attrib)
                
            self.indent(xml, level)
            xml.startElement(name, attributes)
        xml.characters(data._object)
        if name is not None:
            xml.endElement(name)

    def handle_iterable(self, xml, data, level, name):
        add_level = 0
        if name is not None:
            add_level = 1
            attributes = {}
            for attr_name  in data.metadata.get('attributes', []):
                if attr_name in data.fields:
                    attrib = data.fields[attr_name]
                    if attrib._object is not None:
                        attributes[attr_name] = smart_unicode(attrib)
                
            self.indent(xml, level)
            xml.startElement(name, attributes)
        for o in data:
            self._to_xml(xml, o, level+add_level, data.metadata.get('item-name', 'object'))
        if name is not None:
            self.indent(xml, level)
            xml.endElement(name)

    def _to_xml(self, xml, data, level, name=None): 
        if isinstance(data, dict):
            if name is None:
                self.handle_dict(xml, data, level)
            else:
                self.handle_dict(xml, data, level, name)
        elif hasattr(data, '__iter__'):
            self.handle_iterable(xml, data, level, name)
        else:
            self.handle_field(xml, data, level, name)

    def deserialize_stream(self, stream_or_string):
        if isinstance(stream_or_string, basestring):
            stream = StringIO.StringIO(stream_or_string)
        event_stream = iterparse(stream, events=['start', 'end'])
        while True:
            event, node = event_stream.next() # will raise StopIteration exception.
            if node.tag == 'django-objects':
                continue
            data, node = self._to_python(node, event_stream)
            yield data    

    def _to_python(self, start_node, event_stream):
        data = None
        while True:
            event, node = event_stream.next()
            if event == "end": # end of start_node
                assert node == start_node
                if data is None:
                    data = node.text
                break
            else:
                value, node = self._to_python(node, event_stream)
                if data is None:
                    data = {}
                if isinstance(data, dict):
                    if node.tag in data:
                        data = [data[node.tag], value]
                    else:
                        data[node.tag] = value
                elif hasattr(data, '__iter__'):
                    data.append(value)
        if isinstance(data, dict) and node.attrib:
            data.update(node.attrib)
        return data, node
