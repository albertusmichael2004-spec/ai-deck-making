from itertools import combinations

from qa.severity import Severity, issue, report
from state.io import read_yaml


class DeterministicQA:
    """Use native text bounds and actual geometry; do not estimate text overflow."""
    def __init__(self, repository):
        self.rules = read_yaml(repository / "config/qa_rules/deterministic.yaml")

    def check(self, inspection: dict, rendered: dict, allowed_overlaps=(), image_ratios=()):
        issues = []
        if not rendered.get("passed") or len(inspection["slides"]) != len(rendered.get("slides", [])):
            return report([issue("RENDER_INCOMPLETE", Severity.BLOCKER, None, None, "Every slide must have a genuine render")])
        canvas = rendered["canvas_pt"]
        allowed_overlaps = {frozenset(pair) for pair in allowed_overlaps}
        ratio_map = {(row["slide_id"], row["object_id"]): row["expected_ratio"] for row in image_ratios}
        for expected, slide in zip(inspection["slides"], rendered["slides"], strict=True):
            slide_id = expected["slide_id"]
            native = {str(obj["native_id"]): obj for obj in slide["shapes"]}
            participating = []
            for obj in expected["objects"]:
                oid = obj["object_id"]
                actual = native.get(obj["native_id"])
                if actual is None:
                    issues.append(issue("OBJECT_NOT_RENDERED", Severity.BLOCKER, slide_id, oid, "Native object missing from render metrics"))
                    continue
                x, y, width, height = (actual[k] for k in ["x_pt", "y_pt", "width_pt", "height_pt"])
                tolerance = self.rules["geometry_tolerance_pt"]
                if x < -tolerance or y < -tolerance or x + width > canvas["width"] + tolerance or y + height > canvas["height"] + tolerance:
                    issues.append(issue("OUT_OF_BOUNDS", Severity.MAJOR, slide_id, oid, "Object extends beyond the slide canvas"))
                if obj["kind"] != "grpSp": participating.append((oid, actual))
                if obj.get("content_type")=="table":
                    if not actual.get("table_cells"):issues.append(issue("TABLE_METRICS_UNAVAILABLE",Severity.MAJOR,slide_id,oid,"Native table-cell metrics are required"))
                    for cell in actual.get("table_cells",[]):
                        margins=cell["margins_pt"];bounds=cell["text_bounds_pt"];limit=self.rules["text_overflow_tolerance_pt"]
                        if bounds["height"]>cell["height_pt"]-margins["top"]-margins["bottom"]+limit or bounds["width"]>cell["width_pt"]-margins["left"]-margins["right"]+limit:issues.append(issue("TABLE_TEXT_OVERFLOW",Severity.MAJOR,slide_id,oid,"Native table cell exceeds its usable bounds"))
                        if any(run["font_pt"]<self.rules["minimum_font_pt"] for run in cell["runs"]):issues.append(issue("TABLE_FONT_TOO_SMALL",Severity.MAJOR,slide_id,oid,"Native table font is below the readable minimum"))
                if obj.get("content_type")=="chart" and not actual.get("chart_series"):issues.append(issue("CHART_METRICS_UNAVAILABLE",Severity.MAJOR,slide_id,oid,"Native chart values are required"))
                if obj["text"]:
                    if not actual.get("text_bounds_pt") or not actual.get("runs") or "line_count" not in actual:
                        issues.append(issue("TEXT_METRICS_UNAVAILABLE", Severity.MAJOR, slide_id, oid, "Real text layout metrics are required"))
                        continue
                    margin = actual["margins_pt"]
                    bounds = actual["text_bounds_pt"]
                    limit = self.rules["text_overflow_tolerance_pt"]
                    if bounds["height"] > height - margin["top"] - margin["bottom"] + limit or bounds["width"] > width - margin["left"] - margin["right"] + limit:
                        issues.append(issue("TEXT_OVERFLOW", Severity.MAJOR, slide_id, oid, "Native text bounds exceed usable shape dimensions"))
                    if any(run["font_pt"] < self.rules["minimum_font_pt"] for run in actual["runs"]):
                        issues.append(issue("FONT_TOO_SMALL", Severity.MAJOR, slide_id, oid, "A text run is below the minimum readable size"))
                    if obj.get("role") == "title" and actual["line_count"] > self.rules["title_max_lines"]:
                        issues.append(issue("TITLE_TOO_MANY_LINES", Severity.MAJOR, slide_id, oid, "Action title exceeds line-count rule"))
                ratio = ratio_map.get((slide_id, oid))
                if ratio and height > 0 and abs((width / height) / ratio - 1) > self.rules["image_ratio_relative_tolerance"]:
                    issues.append(issue("IMAGE_STRETCH", Severity.MAJOR, slide_id, oid, "Image frame does not preserve the intended cropped aspect ratio"))
            for (first_id, first), (second_id, second) in combinations(participating, 2):
                if frozenset([first_id, second_id]) in allowed_overlaps: continue
                width = max(0, min(first["x_pt"] + first["width_pt"], second["x_pt"] + second["width_pt"]) - max(first["x_pt"], second["x_pt"]))
                height = max(0, min(first["y_pt"] + first["height_pt"], second["y_pt"] + second["height_pt"]) - max(first["y_pt"], second["y_pt"]))
                smaller = min(first["width_pt"] * first["height_pt"], second["width_pt"] * second["height_pt"])
                if smaller > 0 and width * height / smaller > self.rules["overlap_fraction_limit"]:
                    issues.append(issue("UNPLANNED_OVERLAP", Severity.MAJOR, slide_id, first_id, f"Overlap with {second_id} exceeds the declared rule"))
        return report(issues)
