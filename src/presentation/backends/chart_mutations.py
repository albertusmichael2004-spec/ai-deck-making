"""Chart dependency fingerprints and a narrow value-preserving axis repair."""
import hashlib
import posixpath

from presentation.backends.xml import NS,parse,serialize,object_fingerprint
from state.errors import StudioError,ErrorCode

C={**NS,"c":"http://schemas.openxmlformats.org/drawingml/2006/chart"}


def chart_parts(shape,slide_part,package):
    refs=shape.findall(".//c:chart",C)
    if not refs:return []
    rel_name=posixpath.join(posixpath.dirname(slide_part),"_rels",posixpath.basename(slide_part)+".rels")
    relations={row.get("Id"):row for row in parse(package[rel_name][1])}
    result=[]
    for ref in refs:
        relation=relations.get(ref.get(f"{{{NS['r']}}}id"))
        if relation is None or relation.get("TargetMode")=="External":raise StudioError(ErrorCode.SECURITY_BLOCK,"Chart repair requires an internal native chart")
        result.append(posixpath.normpath(posixpath.join(posixpath.dirname(slide_part),relation.get("Target"))))
    return result


def dependency_fingerprint(shape,slide_part,package):
    charts=chart_parts(shape,slide_part,package)
    if not charts:return object_fingerprint(shape)
    visited={};pending=list(charts)
    while pending:
        part=pending.pop()
        if part in visited:continue
        if part not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart dependency is missing")
        visited[part]=hashlib.sha256(package[part][1]).hexdigest()
        rel_name=posixpath.join(posixpath.dirname(part),"_rels",posixpath.basename(part)+".rels")
        if rel_name in package:
            visited[rel_name]=hashlib.sha256(package[rel_name][1]).hexdigest()
            pending.extend(posixpath.normpath(posixpath.join(posixpath.dirname(part),row.get("Target"))) for row in parse(package[rel_name][1]) if row.get("TargetMode")!="External")
    digest=hashlib.sha256(object_fingerprint(shape).encode())
    for name,value in sorted(visited.items()):digest.update(name.encode());digest.update(value.encode())
    return digest.hexdigest()


def repair_axis(shape,slide_part,package,value):
    if value!="zero_origin":raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Only explicit value-preserving zero-origin axis repair is supported")
    parts=chart_parts(shape,slide_part,package)
    if len(parts)!=1:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Axis repair requires one native chart frame")
    name=parts[0];chart=parse(package[name][1])
    bar=chart.find(".//c:barChart",C)
    if bar is None or bar.find("c:barDir",C).get("val")!="bar":raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Zero-origin repair is limited to native horizontal bar charts")
    for axis_tag,crossing in [("catAx","autoZero"),("valAx","max")]:
        axes=chart.findall(".//c:"+axis_tag,C)
        if len(axes)!=1:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Multiple/secondary chart axes require a specific reviewed repair")
        axis=axes[0]
        for row in axis.findall("c:crossesAt",C):axis.remove(row)
        node=axis.find("c:crosses",C)
        if node is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Native axis crossing declaration is absent")
        node.set("val",crossing)
    package[name]=(package[name][0],serialize(chart))
    return name
