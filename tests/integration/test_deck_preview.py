import json
from pathlib import Path

import pytest
from PIL import Image

from cli.main import main
from ir.validation import validate
from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.preview import AnnotationQueue, DeckPreview
from state.errors import StudioError
from state.io import read_json, sha256, write_json


@pytest.fixture
def deck(repo, project):
    spec = read_json(Path(__file__).parents[1] / "fixtures/basic_spec.json")
    transaction = project.begin()
    PresentationCompiler(repo, AdaptiveLayoutCompiler(repo), OOXMLBackend(repo)).compile(**spec, destination=project.candidate(transaction))
    project.commit(transaction, lambda path: {"passed": True, "errors": []})
    # Stand in for the native QA render of this exact deck so no PowerPoint is needed.
    renders = project.path / "work/transactions" / transaction / "renders"
    renders.mkdir(parents=True)
    slides = []
    for index in [1, 2]:
        image = renders / f"slide_{index:03}.png"
        Image.new("RGB", (160, 90), "white").save(image)
        slides.append({"index": index, "render": str(image), "shapes": []})
    write_json(renders / "render_report.json", {"passed": True, "input_sha256": sha256(project.canonical), "slides": slides})
    return OOXMLBackend(repo).inspect(project.canonical)


def body(inspection, slide=0):
    return next(o for o in inspection["slides"][slide]["objects"] if o["role"] == "body")


def test_preview_maps_objects_onto_reused_render_and_caches(repo, project, deck):
    preview = DeckPreview(repo, project).build()
    assert preview["sha256"] == deck["sha256"] and [s["slide_id"] for s in preview["slides"]] == ["s01", "s02"]
    assert all(Path(s["image"]).is_file() for s in preview["slides"])
    boxes = [o["box"] for s in preview["slides"] for o in s["objects"]]
    assert boxes and all(0 <= b["x"] <= 1 and 0 <= b["y"] <= 1 and 0 < b["width"] <= 1 and 0 < b["height"] <= 1 for b in boxes)
    assert any(o["object_id"] == body(deck)["object_id"] for o in preview["slides"][0]["objects"])
    assert DeckPreview(repo, project).build()["generated_at"] == preview["generated_at"]


def test_preview_requires_a_working_deck(repo, project):
    with pytest.raises(StudioError):
        DeckPreview(repo, project).build()


def test_annotations_scope_only_clicked_objects_and_close(repo, project, deck):
    queue = AnnotationQueue(project)
    target = body(deck)
    row = queue.add("s01", [target["object_id"]], "Make this message shorter", region=[0.1, 0.2, 0.3, 0.1])
    assert row["status"] == "pending" and row["objects"][0]["fingerprint"] == target["fingerprint"]
    request = queue.request(deck)
    validate(repo, "edit_scope", request["scope"])
    changeable = [o for o in request["scope"]["objects"] if o["protection"] != "MUST_NOT_CHANGE"]
    assert changeable == [{"slide_id": "s01", "object_id": target["object_id"], "protection": "MAY_CHANGE"}]
    assert request["stale_annotation_ids"] == []
    queue.mark([row["annotation_id"]], "done")
    assert queue.list() == [] and queue.list(include_closed=True)[0]["status"] == "done"
    with pytest.raises(StudioError):
        queue.request(deck)


@pytest.mark.parametrize("slide,objects,text", [("s01", [], "No target"), ("s01", ["missing"], "Unknown"), ("s99", [], "Bad slide"), ("s01", ["x"], "  ")])
def test_annotations_reject_untargeted_or_unknown_input(repo, project, deck, slide, objects, text):
    with pytest.raises(StudioError):
        AnnotationQueue(project).add(slide, objects, text)


def test_annotate_cli_round_trip_writes_revision_scope(repo, project, deck, capsys):
    target = body(deck, 1)
    pid = project.path.name
    assert main(["--root", str(repo), "annotate", "add", pid, "--slide=s02", "--object=" + target["object_id"], "--text=-Use the client's wording"]) == 0
    added = json.loads(capsys.readouterr().out)
    assert added["text"] == "-Use the client's wording"
    assert main(["--root", str(repo), "annotate", "request", pid]) == 0
    request = json.loads(capsys.readouterr().out)
    assert read_json(Path(request["scope_path"])) == request["scope"]
    assert any(step.startswith("studio revise " + pid) for step in request["next_steps"])
    assert main(["--root", str(repo), "annotate", "done", pid, "--id", added["annotation_id"]]) == 0
    capsys.readouterr()
    assert main(["--root", str(repo), "annotate", "list", pid]) == 0
    assert json.loads(capsys.readouterr().out)["annotations"] == []
