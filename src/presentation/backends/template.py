import posixpath
from urllib.parse import unquote

from presentation.backends.xml import NS,parse,serialize
from state.errors import StudioError,ErrorCode


def prepare_template(package,layout_part):
    if layout_part not in package or not layout_part.startswith("ppt/slideLayouts/"):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Requested template layout is absent")
    presentation=parse(package["ppt/presentation.xml"][1]);relations=parse(package["ppt/_rels/presentation.xml.rels"][1])
    slides=presentation.find("p:sldIdLst",NS)
    if slides is not None:
        for row in list(slides):slides.remove(row)
    shows=presentation.find("p:custShowLst",NS)
    if shows is not None:presentation.remove(shows)
    for ext_list in presentation.findall("p:extLst",NS):
        for extension in list(ext_list):
            if any(node.tag.endswith("}sectionLst") for node in extension.iter()):ext_list.remove(extension)
            elif any("sldId" in node.tag for node in extension.iter()):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Template extension references content slides and requires an explicit adapter")
    for relation in list(relations):
        if relation.get("Type","").endswith("/slide"):relations.remove(relation)
    package["ppt/presentation.xml"]=(package["ppt/presentation.xml"][0],serialize(presentation));package["ppt/_rels/presentation.xml.rels"]=(package["ppt/_rels/presentation.xml.rels"][0],serialize(relations))
    reachable={"[Content_Types].xml"};queue=[""]
    while queue:
        part=queue.pop()
        relation_path=posixpath.join(posixpath.dirname(part),"_rels",posixpath.basename(part)+".rels") if part else "_rels/.rels"
        if relation_path not in package:continue
        reachable.add(relation_path)
        for row in parse(package[relation_path][1]):
            if row.get("TargetMode")=="External":continue
            target=unquote(row.get("Target",""))
            target=target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(part),target))
            if target.startswith("../") or target not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Template has an unresolved internal relationship")
            if target not in reachable:reachable.add(target);queue.append(target)
    result={name:value for name,value in package.items() if name in reachable}
    types=parse(result["[Content_Types].xml"][1])
    for row in list(types):
        if row.get("PartName") and row.get("PartName").lstrip("/") not in result:types.remove(row)
    result["[Content_Types].xml"]=(result["[Content_Types].xml"][0],serialize(types))
    if layout_part not in result:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Template layout is unreachable from its master")
    return result
