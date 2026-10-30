"""Bounded DrawingML styling; never touch chart values or embedded workbooks."""
import re
from lxml import etree as ET
from presentation.backends.xml import NS, element, parse, serialize
from presentation.backends.chart_mutations import C, chart_parts
from state.errors import StudioError, ErrorCode

FILLS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}


def replace_fill(properties, fill):
    for node in list(properties):
        if ET.QName(node).localname in FILLS:
            properties.remove(node)
    # Fill follows transform/geometry and precedes line/effects in CT_ShapeProperties.
    index = 0
    for node in properties:
        if ET.QName(node).localname in {"xfrm", "prstGeom", "custGeom"}:
            index = properties.index(node) + 1
    properties.insert(index, fill)


def gradient(shape, value):
    properties = shape.find("p:spPr", NS)
    if properties is None or ET.QName(shape).localname != "sp":
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Gradient fill requires a native shape; convert a connector explicitly first")
    stops = value["stops"]
    if stops[0]["position"] != 0 or stops[-1]["position"] != 1 or any(a["position"] >= b["position"] for a, b in zip(stops, stops[1:])):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Gradient stops must increase strictly from 0 to 1")
    fill = element("a", "gradFill", rotWithShape="1")
    listing = element("a", "gsLst")
    positions = []
    for stop in stops:
        pos = round(stop["position"] * 100000)
        positions.append(pos)
        node = element("a", "gs", pos=str(pos))
        node.append(element("a", "srgbClr", val=stop["color"].upper()))
        listing.append(node)
    if len(set(positions)) != len(positions):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Gradient stops collapse at DrawingML precision")
    fill.append(listing)
    fill.append(element("a", "lin", ang=str(round(value["angle_deg"] * 60000) % 21600000), scaled="1"))
    replace_fill(properties, fill)


def connector_to_shape(shape, value):
    if ET.QName(shape).localname != "cxnSp":
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Conversion requires an existing native connector")
    nonvisual = shape.find("p:nvCxnSpPr", NS)
    properties = shape.find("p:spPr", NS)
    connector = nonvisual.find("p:cNvCxnSpPr", NS) if nonvisual is not None else None
    if properties is None or connector is None:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Connector structure is incomplete")
    from presentation.backends.xml import EMU
    geometry = value["geometry"]
    if any(round(geometry[key]*EMU)<=0 for key in ["width","height"]):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Shape dimensions collapse at DrawingML precision")
    # Keep object ID/name but drop connection endpoints/connector locks.
    nonvisual.replace(connector, element("p", "cNvSpPr"))
    nonvisual.tag = element("p", "nvSpPr").tag
    shape.tag = element("p", "sp").tag
    for node in list(properties):
        if ET.QName(node).localname in {"xfrm", "prstGeom", "custGeom", "ln"}:
            properties.remove(node)
    transform = element("a", "xfrm")
    transform.append(element("a", "off", x=str(round(geometry["x"] * EMU)), y=str(round(geometry["y"] * EMU))))
    transform.append(element("a", "ext", cx=str(round(geometry["width"] * EMU)), cy=str(round(geometry["height"] * EMU))))
    preset = element("a", "prstGeom", prst="rect")
    preset.append(element("a", "avLst"))
    properties.insert(0, transform)
    properties.insert(1, preset)
    line = element("a", "ln")
    line.append(element("a", "noFill"))
    properties.insert(2 + sum(ET.QName(n).localname in FILLS for n in properties), line)


def chart_colors(shape, slide_part, package, value):
    parts = chart_parts(shape, slide_part, package)
    if len(parts) != 1:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Color edit requires one internal native chart")
    name = parts[0]
    chart = parse(package[name][1])
    series = chart.findall("c:chart/c:plotArea/*/c:ser", C)
    seen = set()
    for request in value["series"]:
        index = request["index"]
        if index >= len(series) or index in seen:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Chart series index is missing or duplicated")
        seen.add(index)
        target = series[index]
        if ET.QName(target.getparent()).localname not in {"barChart","bar3DChart","pieChart","pie3DChart","doughnutChart","areaChart","area3DChart","bubbleChart"}:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Palette operation currently supports filled native chart series; line/marker palettes need a dedicated reviewed operation")
        if request["color"] is not None:
            _chart_fill(target, request["color"], before={"spPr", "marker", "explosion", "invertIfNegative", "pictureOptions", "dPt", "dLbls", "trendline", "errBars", "cat", "val", "xVal", "yVal", "bubbleSize", "bubble3D", "smooth", "shape", "extLst"})
        points = set()
        caches = target.findall("c:val/c:numRef/c:numCache", C) + target.findall("c:val/c:numLit", C) + target.findall("c:yVal/c:numRef/c:numCache", C) + target.findall("c:yVal/c:numLit", C)
        available = {int(p.get("idx")) for cache in caches for p in cache.findall("c:pt", C)}
        for point in request["points"]:
            idx = point["index"]
            if idx not in available or idx in points:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Chart point index is missing or duplicated; a native value cache is required")
            points.add(idx)
            matches = [p for p in target.findall("c:dPt", C) if p.find("c:idx", C) is not None and int(p.find("c:idx", C).get("val")) == idx]
            if len(matches) > 1:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Duplicate native chart point overrides")
            node = matches[0] if matches else ET.Element("{" + C["c"] + "}dPt")
            if not matches:
                node.append(ET.Element("{" + C["c"] + "}idx", val=str(idx)))
                _insert_before(target, node, {"dLbls", "trendline", "errBars", "cat", "val", "xVal", "yVal", "bubbleSize", "smooth", "extLst"})
            _chart_fill(node, point["color"], before={"pictureOptions", "extLst"})
        if request["color"] is None and not request["points"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Chart color request has no changes")
    package[name] = (package[name][0], serialize(chart))
    return name


def _insert_before(parent, node, tags):
    index = next((i for i, child in enumerate(parent) if ET.QName(child).localname in tags), len(parent))
    parent.insert(index, node)


def _chart_fill(parent, color, before):
    if not re.fullmatch(r"[0-9a-fA-F]{6}", color):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Chart color requires RGB hex")
    properties = parent.find("c:spPr", C)
    if properties is None:
        properties = ET.Element("{" + C["c"] + "}spPr")
        _insert_before(parent, properties, before)
    fill = element("a", "solidFill")
    fill.append(element("a", "srgbClr", val=color.upper()))
    replace_fill(properties, fill)
