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


class TypeField(field.Field):
    def get_object(self, obj, field_name):
        field, _, _, _ = obj._meta.get_field_by_name(field_name)
        return field.get_internal_type()


class ModelWithAttributes(field.ModelField):
    type = TypeField()

    def metadata(self, metadict):
        metadict['attributes'] = ['type']
        return metadict

    def get_object(self, obj, field_name):
        field = obj._meta.get_field_by_name(field_name)[0]
        if getattr(obj, field_name) is not None:
            return field.value_to_string(obj)
        else:
            return None


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
        if obj is not None:
            return smart_unicode(obj)
        else:
            return obj


class XmlM2mRelatedField(field.M2mRelatedField):
    def serialize_object(self, obj): # get_object from RelatedField won't be called
        serialized = super(XmlM2mRelatedField, self).serialize_object(obj)
        if hasattr(serialized, '__iter__'):
            return [smart_unicode(o) for o in serialized]
        else:
            return smart_unicode(serialized)


class M2mWithAttributes(field.M2mField):
    rel = RelField()
    to = ToField()

    def __init__(self, label=None, use_natural_keys=False, related_field=XmlM2mRelatedField):
        super(M2mWithAttributes, self).__init__(label=label, use_natural_keys=use_natural_keys)
        self.related_field = related_field
    
    def metadata(self, metadict):
        metadict['attributes'] = ['rel', 'to']
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
        if self.options.get('indent', None) is not None:
            xml.ignorableWhitespace('\n' + ' ' * self.options.get('indent', None) * level)
    
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
            for attr_name  in getattr(data, 'metadata', {}).get('attributes', []):
                if attr_name in data.fields:
                    attrib = data.fields[attr_name]
                    if attrib is not None:
                        attributes[attr_name] = smart_unicode(attrib)
                
            self.indent(xml, level)
            xml.startElement(name, attributes)
        val = getattr(data, '_object', data)
        if val is not None:
            xml.characters(val)
        else:
            xml.addQuickElement("None")
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
        else:
            stream = stream_or_string
        event_stream = iterparse(stream, events=['start', 'end'])
        while True:
            event, node = event_stream.next() # will raise StopIteration exception.
            if node.tag == 'django-objects':
                continue
            data, node = self._to_python(node, event_stream)
            yield data    
   

    def de_handle_m2m_field(self, start_node, event_stream):
        data = []
        event, node = event_stream.next()
        while node != start_node:
            value, node = self._to_python(node, event_stream)
            data.append(value)
            event, node = event_stream.next()
        
        return data, node
    
    def de_handle_fk_field(self, start_node, event_stream):
        event, node = event_stream.next()
        data = None
        if event == "end": # end of start_node
            assert node == start_node
            data = node.text or ""
        elif node.tag == "None":
            event_stream.next() # end None tag
            event, node = event_stream.next() # end start_node
            assert node == start_node
            data = None
        else: 
            data = []
            while node != start_node:
                value, node = self._to_python(node, event_stream)
                data.append(value)
                event, node = event_stream.next()
        return data, node



    def _to_python(self, start_node, event_stream):
        if 'rel' in start_node.attrib:
            if start_node.attrib['rel'] == "ManyToManyRel":
                return self.de_handle_m2m_field(start_node, event_stream)
            else:
                return self.de_handle_fk_field(start_node, event_stream)

        event, node = event_stream.next()
        data = None
        if event == "end": # end of start_node
            assert node == start_node
            data = node.text or ""
        elif node.tag == "None":
            event_stream.next() # end None tag
            event, node = event_stream.next() # end start_node
            assert node == start_node
            data = None
        else:
            data = {}
            while node != start_node:
                value, node = self._to_python(node, event_stream)
                if isinstance(data, dict):
                    if node.tag in data:
                        data = [data[node.tag], value]
                    else:
                        data[node.tag] = value
                elif hasattr(data, '__iter__'):
                    data.append(value)
                    
                event, node = event_stream.next()
            if isinstance(data, dict) and node.attrib:
                data.update(node.attrib)
        return data, node
