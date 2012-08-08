"""
XML serializer.
"""
import StringIO
from xml.etree.ElementTree import iterparse

from django.conf import settings
from django.utils.xmlutils import SimplerXMLGenerator
from django.utils.encoding import smart_unicode

from django.core.serializers import  native
from django.core.serializers import base
from django.core.serializers import field
from django.core.serializers.utils import ObjectWithMetadata


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
    name = NameField() 
    rel = RelField()
    to = ToField()

    def metadata(self, metadict):
        metadict['attributes'] = ['name', 'rel', 'to']
        return metadict

    def serialize_object(self, obj):
        return smart_unicode(obj)


class M2mWithAttributes(field.M2mField):
    name = NameField() 
    rel = RelField()
    to = ToField()

    def metadata(self, metadict):
        metadict['attributes'] = ['name', 'rel', 'to']
        return metadict


class FieldsSerializer(native.ModelSerializer):
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
    
    def serialize_objects(self, obj):
        xml = SimplerXMLGenerator(self.stream, settings.DEFAULT_CHARSET)
        xml.startDocument()
        xml.startElement("django-objects", {"version" : "1.0"})
        level = 0
        self._to_xml(xml, obj, level + 1)
        self.indent(xml, level)
        xml.endElement("django-objects")
        xml.endDocument()
    
    def handle_object(self, xml, data, level):
        name = "object"
        attributes = {}
        for attr_name  in data.metadata.get('attributes', []):
            if attr_name in data:
                attrib = data.pop(attr_name)
                if attrib._object is not None:
                    attributes[attr_name] = smart_unicode(attrib)
                
        self.indent(xml, level)
        xml.startElement(name, attributes)
        for key, value in data['field'].items():
            self.handle_field(xml, value, level + 1)
        self.indent(xml, level)
        xml.endElement(name)

    def handle_field(self, xml, data, level, name="field"):
        attributes = {}
        for attr_name  in data.metadata.get('attributes', []):
            attrib = None
            if attr_name in data.fields:
                attrib = data.fields[attr_name]
            elif isinstance(data, dict) and attr_name in data:
                attrib = data.pop(attr_name)
            
            if attrib is not None:
                attributes[attr_name] = attrib
                
        self.indent(xml, level)
        xml.startElement(name, attributes)
        
        if hasattr(data, '__iter__'):
            if 'rel' in attributes and attributes['rel']._object == "ManyToManyRel":
                for item in data:
                    self.handle_m2m_field(xml, item, level + 1)
            else: #natural keys
                self.handle_natural_keys(xml, data, level + 1)
            self.indent(xml, level)
        else:
            xml.characters(data._object)
        xml.endElement(name)

    def handle_natural_keys(self, xml, data, level):
        for o in data:
            self.indent(xml, level)
            xml.startElement("natural", {})
            xml.characters(getattr(o, '_object', o))
            xml.endElement("natural")

    def handle_m2m_field(self, xml, data, level, name="object"):
        if hasattr(data, '__iter__'): # natural keys
            self.indent(xml, level)
            xml.startElement(name, {})
            self.handle_natural_keys(xml, data, level + 1) 
            self.indent(xml, level)
            xml.endElement(name)

        else:
            attributes = {'pk' : smart_unicode(data._object)}
            self.indent(xml, level)
            xml.startElement(name, attributes)
            xml.endElement(name)
   
    def _to_xml(self, xml, data, level): 
        if isinstance(data, dict):
                self.handle_object(xml, data, level)
        elif hasattr(data, '__iter__'):
            for item in data:
                self._to_xml(xml, item, level)
        else:
            xml.characters(data._object)

    def deserialize_stream(self, stream_or_string):
        if isinstance(stream_or_string, basestring):
            stream = StringIO.StringIO(stream_or_string)
        event_stream = iterparse(stream, events=['start', 'end'])
        while True:
            event, node = event_stream.next() # will raise StopIteration exception.
            if node.tag == 'django-objects':
                continue
            data, node = self.de_handle_object(node, event_stream)
            yield data    

    def de_handle_object(self, start_node, event_stream):
        data = {'field' : {}}
        while True:
            event, node = event_stream.next()
            if event == "end": # end of start_node
                assert node == start_node
                data.update(node.attrib)
                break
            else:
                name, value, node = self.de_handle_field(node, event_stream)
                data['field'][name] = value
        return data, node

    def de_handle_field(self, start_node, event_stream):
        event, node = event_stream.next()
        if event == "end": # end of start_node
            name = node.attrib['name']
            data = node.text
            return name, data, node
        else: 
            #  m2m o natural key
            name = start_node.attrib['name']
            if 'rel' in start_node.attrib and start_node.attrib['rel'] == "ManyToManyRel":
                # m2m
                m2m_pk = []
                while node.tag != 'field':
                    data = self.de_handle_m2m_field(node, event_stream)
                    m2m_pk.append(data)
                    event, node = event_stream.next()
                return name, m2m_pk, node
            else: # natural key
                natural_keys, node  = self.de_handle_natural_keys(node, event_stream)
                return name, natural_keys, node

    def de_handle_natural_keys(self, start_node, event_stream):
        keys = []
        node = start_node
        while node.tag not in ['field', 'object']:
            data = self._de_handle_natural_keys(node, event_stream)
            keys.append(data)
            event, node = event_stream.next()
        return keys, node

    def _de_handle_natural_keys(self, node, event_stream):
        event, node = event_stream.next()
        return node.text

    
    def de_handle_m2m_field(self, start_node, event_stream):
        event, node = event_stream.next()
        if node != start_node: # natural key
            natural_keys, node  = self.de_handle_natural_keys(node, event_stream)
            return natural_keys
        else:
            return node.attrib['pk']
