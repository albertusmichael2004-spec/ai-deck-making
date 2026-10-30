from pathlib import Path

from PIL import Image, ImageChops

from qa.severity import Severity, issue, report


def protected_scope(before: dict, after: dict, scope: dict):
    def protected_value(obj):
        # Chart/workbook and table data live outside a shape's XML fingerprint.
        return {key:value for key,value in obj.items() if key not in {"native_id","geometry","role","text","table_selected_cells"}}
    originals = {(s["slide_id"], o["object_id"]): protected_value(o) for s in before["slides"] for o in s["objects"]}
    modified = {(s["slide_id"], o["object_id"]): protected_value(o) for s in after["slides"] for o in s["objects"]}
    allowed = {(o["slide_id"], o["object_id"]) for o in scope["objects"] if o["protection"] in {"MUST_CHANGE", "MAY_CHANGE"}}
    issues = []
    for key in originals.keys() | modified.keys():
        if originals.get(key) != modified.get(key) and key not in allowed:
            issues.append(issue("UNAUTHORIZED_CHANGE", Severity.BLOCKER, *key, "Object outside requested scope changed"))
    return report(issues)


def pixel_compare(before: Path, after: Path, tolerance: int, changed_fraction_limit: float):
    with Image.open(before) as original, Image.open(after) as modified:
        if original.size != modified.size:
            return {"passed": False, "reason": "render_dimensions_changed", "changed_fraction": 1.0}
        difference = ImageChops.difference(original.convert("RGB"), modified.convert("RGB"))
        # Count pixels whose largest RGB channel difference exceeds calibrated tolerance.
        channels = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        histogram = maximum.histogram()
        changed = sum(histogram[tolerance + 1:])
        fraction = changed / (original.width * original.height)
        return {"passed": fraction <= changed_fraction_limit, "changed_fraction": fraction, "tolerance": tolerance, "limit": changed_fraction_limit}
