from lxml import etree as ET
from ir.identity import numeric_id
from state.errors import ErrorCode, StudioError
from presentation.backends.xml import NS, EMU, element


def make_slide(slide):
    node = ET.Element(f"{{{NS['p']}}}sld", nsmap={k: NS[k] for k in ["p", "a", "r"]})
    common = element("p", "cSld", name="studio:" + slide["slide_id"])
    node.append(common)
    background = element("p", "bg")
    background_properties = element("p", "bgPr")
    background_fill = element("a", "solidFill")
    background_fill.append(element("a", "srgbClr", val=slide["background"]))
    background_properties.extend([background_fill, element("a", "effectLst")])
    background.append(background_properties)
    common.append(background)
    tree = element("p", "spTree")
    common.append(tree)
    nonvisual = element("p", "nvGrpSpPr")
    nonvisual.extend([element("p", "cNvPr", id=1, name=""), element("p", "cNvGrpSpPr"), element("p", "nvPr")])
    tree.append(nonvisual)
    group_properties = element("p", "grpSpPr")
    group_transform = element("a", "xfrm")
    for local, props in [("off", {"x": 0, "y": 0}), ("ext", {"cx": 0, "cy": 0}), ("chOff", {"x": 0, "y": 0}), ("chExt", {"cx": 0, "cy": 0})]:
        group_transform.append(element("a", local, **props))
    group_properties.append(group_transform)
    tree.append(group_properties)
    seen = {1}
    for item in slide["objects"]:
        identifier = numeric_id(item["object_id"])
        if identifier in seen:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Deterministic object ID collision")
        seen.add(identifier)
        shape = element("p", "sp")
        nv = element("p", "nvSpPr")
        nv.extend([element("p", "cNvPr", id=identifier, name="studio:" + item["object_id"], descr="studio-role:" + item.get("role", "body")), element("p", "cNvSpPr", txBox="1" if item["kind"] == "text" else "0"), element("p", "nvPr")])
        shape.append(nv)
        properties = element("p", "spPr")
        transform = element("a", "xfrm")
        if item.get("flip_h"):transform.set("flipH","1")
        if item.get("flip_v"):transform.set("flipV","1")
        transform.extend([element("a", "off", x=round(item["x"] * EMU), y=round(item["y"] * EMU)), element("a", "ext", cx=round(item["width"] * EMU), cy=round(item["height"] * EMU))])
        properties.append(transform)
        geometry = element("a", "prstGeom", prst=item.get("geometry","rect"))
        geometry.append(element("a", "avLst"))
        properties.append(geometry)
        fill = element("a", "solidFill") if "fill" in item else element("a", "noFill")
        if "fill" in item: fill.append(element("a", "srgbClr", val=item["fill"]))
        properties.append(fill)
        line = element("a", "ln")
        if item.get("geometry")=="line":
            line_fill=element("a","solidFill");line_fill.append(element("a","srgbClr",val=item.get("color","176B87")));line.append(line_fill)
        else:line.append(element("a", "noFill"))
        properties.append(line)
        shape.append(properties)
        if item["kind"] == "text":
            body = element("p", "txBody")
            body.extend([element("a", "bodyPr", wrap="square", lIns=0, rIns=0, tIns=0, bIns=0), element("a", "lstStyle")])
            for line_text in item.get("text", "").split("\n"):
                paragraph = element("a", "p")
                if item.get("align"):paragraph.append(element("a","pPr",algn={"left":"l","center":"ctr","right":"r"}[item["align"]]))
                run = element("a", "r")
                props = element("a", "rPr", lang="en-US", sz=round(item.get("font_pt", 20) * 100), b="1" if item.get("bold") else "0")
                solid = element("a", "solidFill")
                solid.append(element("a", "srgbClr", val=item.get("color", "172B4D")))
                props.extend([solid, element("a", "latin", typeface=item.get("font_family","Arial"))])
                text = element("a", "t")
                text.text = line_text
                run.extend([props, text])
                paragraph.append(run)
                body.append(paragraph)
            shape.append(body)
        tree.append(shape)
    color_map = element("p", "clrMapOvr")
    color_map.append(element("a", "masterClrMapping"))
    node.append(color_map)
    return node

