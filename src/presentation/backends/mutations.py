import copy
from lxml import etree as ET
from state.errors import ErrorCode, StudioError
from presentation.backends.xml import NS, EMU, element


def apply_operation(shape, operation):
    value = operation["value"]
    if operation["operation"] == "set_text":
        if not isinstance(value, str):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Text patch requires string")
        body = shape.find("p:txBody", NS)
        if body is None:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Object is not a native text shape")
        first_props = body.find("a:p/a:r/a:rPr", NS)
        preserved = copy.deepcopy(first_props) if first_props is not None else element("a", "rPr")
        for paragraph in list(body.findall("a:p", NS)): body.remove(paragraph)
        for line in value.split("\n"):
            paragraph, run, text = element("a", "p"), element("a", "r"), element("a", "t")
            text.text = line
            run.extend([copy.deepcopy(preserved), text])
            paragraph.append(run)
            body.append(paragraph)
    elif operation["operation"] == "set_geometry":
        import math
        if not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"} or any(type(v) not in {int, float} or not math.isfinite(v) for v in value.values()) or value["width"] <= 0 or value["height"] <= 0:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid geometry patch")
        transform = shape.find("p:spPr/a:xfrm", NS)
        if transform is None: transform = shape.find("p:xfrm", NS)
        if transform is None:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Geometry patch unsupported for this object")
        transform.find("a:off", NS).attrib.update({"x":str(round(value["x"] * EMU)), "y":str(round(value["y"] * EMU))})
        transform.find("a:ext", NS).attrib.update({"cx":str(round(value["width"] * EMU)), "cy":str(round(value["height"] * EMU))})
    elif operation["operation"] in {"set_gradient_fill", "connector_to_shape"}:
        from presentation.backends.styles import gradient, connector_to_shape
        (gradient if operation["operation"] == "set_gradient_fill" else connector_to_shape)(shape, value)
    elif operation["operation"] == "set_fill":
        import re
        if not isinstance(value, str) or not re.fullmatch(r"[A-Fa-f0-9]{6}", value):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Fill patch requires RGB hex")
        properties = shape.find("p:spPr", NS)
        if properties is None:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Fill patch unsupported for this object")
        for child in list(properties):
            if ET.QName(child).localname in {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}: properties.remove(child)
        fill = element("a", "solidFill")
        fill.append(element("a", "srgbClr", val=value))
        geometry = properties.find("a:prstGeom", NS)
        properties.insert(properties.index(geometry) + 1 if geometry is not None else 1, fill)
    else:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Unsupported shape operation", operation=operation["operation"])

