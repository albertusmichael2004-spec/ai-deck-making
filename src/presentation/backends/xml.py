import hashlib
from lxml import etree as ET
from state.errors import ErrorCode, StudioError

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "rel": "http://schemas.openxmlformats.org/package/2006/relationships", "ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
EMU = 914400
SHAPES = {f"{{{NS['p']}}}{tag}" for tag in ["sp", "pic", "graphicFrame", "grpSp", "cxnSp"]}


def element(prefix, local, **attributes):
    return ET.Element(f"{{{NS[prefix]}}}{local}", {key: str(value) for key, value in attributes.items()})


def parse(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise StudioError(ErrorCode.SECURITY_BLOCK, "OOXML document types and entities are forbidden")
    try:
        return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))
    except ET.XMLSyntaxError as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid OOXML") from exc


def serialize(node):
    return ET.tostring(node, xml_declaration=True, encoding="UTF-8", standalone=True)


def object_fingerprint(node):
    return hashlib.sha256(ET.tostring(node, method="c14n")).hexdigest()

