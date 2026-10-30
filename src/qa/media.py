import io
import posixpath

from PIL import Image, UnidentifiedImageError

from presentation.backends.xml import NS, parse
from state.errors import StudioError, ErrorCode


def image_ratios(backend, source):
    package = backend._read(source)
    _, slides = backend._slide_entries(package)
    result = []
    for slide_id, name, node in slides:
        relationship_name = posixpath.dirname(name) + "/_rels/" + posixpath.basename(name) + ".rels"
        if relationship_name not in package: continue
        relationships = parse(package[relationship_name][1])
        targets = {r.attrib["Id"]: posixpath.normpath(posixpath.join(posixpath.dirname(name), r.attrib["Target"])) for r in relationships if r.attrib.get("TargetMode") != "External"}
        for oid, shape, props in backend._objects(node):
            blip = shape.find("p:blipFill/a:blip", NS)
            if blip is None: continue
            target = targets.get(blip.get(f"{{{NS['r']}}}embed"))
            if target not in package:
                raise StudioError(ErrorCode.QA_FAILURE, "Broken image relationship", slide_id=slide_id, object_id=oid)
            try:
                with Image.open(io.BytesIO(package[target][1])) as image:
                    width, height = image.size
                    image.verify()
            except (UnidentifiedImageError, OSError) as exc:
                raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Image format cannot be verified safely", part=target) from exc
            crop = shape.find("p:blipFill/a:srcRect", NS)
            horizontal = 1 - (int(crop.get("l", 0)) + int(crop.get("r", 0))) / 100000 if crop is not None else 1
            vertical = 1 - (int(crop.get("t", 0)) + int(crop.get("b", 0))) / 100000 if crop is not None else 1
            if horizontal <= 0 or vertical <= 0 or height <= 0:
                raise StudioError(ErrorCode.QA_FAILURE, "Invalid image crop")
            result.append({"slide_id": slide_id, "object_id": oid, "expected_ratio": width * horizontal / (height * vertical), "part": target})
    return result
