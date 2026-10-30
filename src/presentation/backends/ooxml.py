import hashlib
import io
import posixpath
import zipfile
from pathlib import Path

from lxml import etree as ET

from ir.identity import numeric_id
from ir.validation import validate as validate_schema
from presentation.mutation.scope import validate_scope
from security.files import FileRegistry
from security.paths import PathPolicy
from state.errors import ErrorCode, StudioError
from state.io import atomic_bytes, native_path, read_yaml, sha256,open_read


from presentation.backends.xml import NS, EMU, SHAPES, parse, serialize, object_fingerprint, element
from presentation.backends.native_shapes import make_slide
from presentation.backends.mutations import apply_operation
from presentation.backends.chart_mutations import dependency_fingerprint,repair_axis


class OOXMLBackend:
    """Mutate selected XML leaves and preserve every untouched ZIP payload."""
    def __init__(self, repository: Path):
        self.repository = repository
        limits = read_yaml(repository / "config/security/files.yaml")
        self.policy = PathPolicy([repository], [repository / "projects", repository / "runtime", repository / "tests"], [repository / "library/knowledge/packages"])
        self.registry = FileRegistry(self.policy, limits)

    def capabilities(self):
        return {"backend": "OOXMLBackend", "version": "1.2", "supports": {"text": True, "shapes": True, "gradient_fill": True, "connector_to_shape": True, "chart_colors": True, "native_charts": True, "groups_edit": False, "notes_edit": False, "preserve_untouched_parts": True, "animation_preservation": True, "live_attach": False, "active_selection_read": False, "comments_read": False, "render": False}}

    def _read(self, path):
        self.registry.inspect(path, "canonical_target")
        with open_read(path) as incoming,zipfile.ZipFile(incoming) as archive:
            return {info.filename: (info, archive.read(info)) for info in archive.infolist()}

    def _write(self, package, destination):
        target = self.policy.check(destination, write=True)
        # Backend never writes canonical directly; Project owns the commit boundary.
        if target.name == "canonical.pptx" or "input" in target.relative_to(native_path(self.repository)).parts:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Compile to a working copy, then use project.commit")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, (info, data) in package.items():
                archive.writestr(info if info else name, data)
        atomic_bytes(target, stream.getvalue())

    @staticmethod
    def _slide_entries(package):
        presentation = parse(package["ppt/presentation.xml"][1])
        relationships = parse(package["ppt/_rels/presentation.xml.rels"][1])
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships if r.attrib.get("Type", "").endswith("/slide")}
        entries = []
        for item in presentation.findall("p:sldIdLst/p:sldId", NS):
            relation = item.attrib[f"{{{NS['r']}}}id"]
            if relation not in targets:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unresolved slide relationship")
            name = posixpath.normpath(posixpath.join("ppt", targets[relation]))
            if not name.startswith("ppt/slides/") or name not in package:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Slide relationship points outside slide package")
            node = parse(package[name][1])
            custom = node.find("p:cSld", NS).get("name", "")
            slide_id = custom[7:] if custom.startswith("studio:") else "slide-" + item.attrib["id"]
            entries.append((slide_id, name, node))
        return presentation, entries

    @staticmethod
    def _objects(node):
        for item in node.iter():
            if item.tag not in SHAPES:
                continue
            props = item.find(".//p:cNvPr", NS)
            if props is not None:
                name = props.get("name", "")
                identity = name[7:] if name.startswith("studio:") else "shape-" + props.get("id", "")
                yield identity, item, props

    def inspect(self, source):
        package = self._read(source)
        presentation, slides = self._slide_entries(package)
        size = presentation.find("p:sldSz", NS)
        result = []
        for slide_id, name, node in slides:
            objects = []
            identities = set()
            for identity, shape, props in self._objects(node):
                if identity in identities:
                    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Duplicate slide object identity")
                identities.add(identity)
                transform = shape.find("p:spPr/a:xfrm", NS)
                if transform is None: transform = shape.find("p:xfrm", NS)
                if transform is None: transform = shape.find("p:grpSpPr/a:xfrm", NS)
                geometry = None
                if transform is not None:
                    off, ext = transform.find("a:off", NS), transform.find("a:ext", NS)
                    if off is not None and ext is not None:
                        geometry = {"x": int(off.get("x")) / EMU, "y": int(off.get("y")) / EMU, "width": int(ext.get("cx")) / EMU, "height": int(ext.get("cy")) / EMU}
                description = props.get("descr", "")
                role = description[12:] if description.startswith("studio-role:") else None
                placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if placeholder is not None and placeholder.get("type") in {"title", "ctrTitle"}: role = "title"
                objects.append({"object_id": identity, "native_id": props.get("id"), "kind": ET.QName(shape).localname, "role": role, "text": "\n".join("".join(p.itertext()) for p in shape.findall("p:txBody/a:p", NS)), "fingerprint": dependency_fingerprint(shape,name,package), "geometry": geometry})
            result.append({"slide_id": slide_id, "part": name, "objects": objects})
            for identity,shape,props in self._objects(node):
                item=next(item for item in objects if item["object_id"]==identity)
                from presentation.backends.business_inspection import inspect_business
                item.update(inspect_business(shape,name,package))
        return {"schema_version": "1.0", "backend": "OOXMLBackend", "sha256": sha256(source), "canvas": {"width_in": int(size.get("cx")) / EMU, "height_in": int(size.get("cy")) / EMU}, "slides": result, "parts": len(package)}

    def validate(self, source):
        try:
            package = self._read(source)
            for name, (_, data) in package.items():
                if name.endswith((".xml", ".rels")): parse(data)
            inspection = self.inspect(source)
            if not inspection["slides"]:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Deck has no slides")
            slide_ids = [slide["slide_id"] for slide in inspection["slides"]]
            if len(slide_ids) != len(set(slide_ids)):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Duplicate slide identities")
            return {"passed": True, "errors": [], "scope": "structural_only", "rendered": False}
        except StudioError as exc:
            return {"passed": False, "errors": [exc.as_dict()], "rendered": False}

    def create(self, slides, canvas, destination, template=None):
        from importlib.resources import files
        layout_part="ppt/slideLayouts/slideLayout7.xml"
        if template:
            from presentation.backends.template import prepare_template
            layout_part=template["layout_part"]
            package=prepare_template(self._read(Path(template["path"])),layout_part)
        else:
            default_template = files("pptx").joinpath("templates/default.pptx")
            with zipfile.ZipFile(default_template) as archive:
                package = {i.filename: (i, archive.read(i)) for i in archive.infolist()}
        presentation = parse(package["ppt/presentation.xml"][1])
        rels = parse(package["ppt/_rels/presentation.xml.rels"][1])
        types = parse(package["[Content_Types].xml"][1])
        slide_list = presentation.find("p:sldIdLst", NS)
        if slide_list is None:
            slide_list = element("p", "sldIdLst")
            master_list = presentation.find("p:sldMasterIdLst", NS)
            presentation.insert(presentation.index(master_list) + 1, slide_list)
        size = presentation.find("p:sldSz", NS)
        if template and any(abs(int(size.get(key))/EMU-canvas[field])>1e-5 for key,field in [("cx","width_in"),("cy","height_in")]):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Template canvas must match the requested deck; preserving master geometry requires an explicit matching canvas")
        size.set("cx", str(round(canvas["width_in"] * EMU)))
        size.set("cy", str(round(canvas["height_in"] * EMU)))
        numeric_ids = set()
        for index, slide in enumerate(slides):
            slide_id = slide["slide_id"]
            identifier = numeric_id(slide_id)
            if identifier in numeric_ids:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Deterministic slide ID collision")
            numeric_ids.add(identifier)
            relation_id = "studioSlide" + str(index)
            name = f"ppt/slides/studio_{slide_id}.xml"
            slide_list.append(element("p", "sldId", id=identifier, **{f"{{{NS['r']}}}id": relation_id}))
            rels.append(element("rel", "Relationship", Id=relation_id, Type=NS["r"] + "/slide", Target="slides/" + Path(name).name))
            types.append(element("ct", "Override", PartName="/" + name, ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"))
            simple={**slide,"objects":[item for item in slide["objects"] if item["kind"] in {"text","shape"}]}
            package[name] = (None, serialize(make_slide(simple)))
            slide_rels = element("rel", "Relationships")
            slide_rels.append(element("rel", "Relationship", Id="rId1", Type=NS["r"] + "/slideLayout", Target=posixpath.relpath(layout_part,"ppt/slides")))
            package[f"ppt/slides/_rels/studio_{slide_id}.xml.rels"] = (None, serialize(slide_rels))
        for name, node in [("ppt/presentation.xml", presentation), ("ppt/_rels/presentation.xml.rels", rels), ("[Content_Types].xml", types)]:
            package[name] = (package[name][0], serialize(node))
        if any(item["kind"] in {"chart","table"} for slide in slides for item in slide["objects"]):
            from presentation.backends.business_objects import augment
            package=augment(package,slides)
        self._write(package, destination)
        result = self.validate(destination)
        if not result["passed"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Created deck failed structural validation", errors=result["errors"])
        return self.inspect(destination)


    def patch(self, source, destination, patch, scope):
        validate_schema(self.repository, "patch_spec", patch)
        validate_schema(self.repository, "edit_scope", scope)
        required = validate_scope(patch, scope)
        package = self._read(source)
        _, slides = self._slide_entries(package)
        slide_map = {identity: (name, node) for identity, name, node in slides}
        originals = {(sid, oid): dependency_fingerprint(shape,name,package) for sid, name, node in slides for oid, shape, _ in self._objects(node)}
        changed_parts, changed_targets = set(), set()
        before_hashes = {name: hashlib.sha256(data).hexdigest() for name, (_, data) in package.items()}
        for operation in patch["operations"]:
            if operation["slide_id"] not in slide_map:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Slide does not exist")
            name, node = slide_map[operation["slide_id"]]
            objects = {identity: item for identity, item, _ in self._objects(node)}
            shape = objects.get(operation["object_id"])
            if shape is None:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Object does not exist")
            if originals[(operation["slide_id"], operation["object_id"])] != operation["expected_fingerprint"]:
                raise StudioError(ErrorCode.FILE_CONFLICT, "Object changed since patch planning")
            if operation["operation"]=="set_chart_colors":
                from presentation.backends.styles import chart_colors
                changed_parts.add(chart_colors(shape,name,package,operation["value"]))
            elif operation["operation"]=="repair_chart_axis":changed_parts.add(repair_axis(shape,name,package,operation["value"]))
            else:
                apply_operation(shape, operation)
                changed_parts.add(name)
            if dependency_fingerprint(shape,name,package) != operation["expected_fingerprint"]:
                changed_targets.add((operation["slide_id"], operation["object_id"]))
        if not required <= changed_targets:
            raise StudioError(ErrorCode.QA_FAILURE, "Required objects were not changed")
        current = {(sid, oid): dependency_fingerprint(shape,name,package) for sid, (name, node) in slide_map.items() for oid, shape, _ in self._objects(node)}
        for protected in scope["objects"]:
            key = (protected["slide_id"], protected["object_id"])
            if protected["protection"] == "MUST_NOT_CHANGE" and (key not in originals or current.get(key) != originals[key]):
                raise StudioError(ErrorCode.QA_FAILURE, "Protected object changed, including group descendants")
        for name, node in slide_map.values():
            if name in changed_parts:
                package[name] = (package[name][0], serialize(node))
        for name, expected in before_hashes.items():
            if name not in changed_parts and hashlib.sha256(package[name][1]).hexdigest() != expected:
                raise StudioError(ErrorCode.QA_FAILURE, "Untouched part changed")
        self._write(package, destination)
        validation = self.validate(destination)
        if not validation["passed"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Patched package failed validation", errors=validation["errors"])
        return {"passed": True, "changed_parts": sorted(changed_parts), "changed_targets": sorted(changed_targets), "structural": validation}

