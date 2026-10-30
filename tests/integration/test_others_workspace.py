import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from cli import codex_launcher
from cli.main import main
from cli.workspace_menu import ProjectMenu
from state.errors import StudioError, ErrorCode
from state.io import fingerprint, logical_path, read_json, sha256, write_json
from state.outputs import export_others
from state.project import Project
from state.workspace import Workspaces


ROOT = Path(__file__).resolve().parents[2]


def kernel_quick(repo):
    workspaces = Workspaces(repo)
    project = Project.create(repo, "others-" + "a" * 32, others=True, validation_policy="kernel")
    workspaces.register(project, "Others")
    value = workspaces.metadata(project)
    value["category"] = "others"
    workspaces.save(project, value)
    return workspaces, project


def commit(project, content):
    transaction = project.begin()
    project.candidate(transaction).write_bytes(content)
    project.commit(transaction, lambda _path: {"passed": True, "errors": []})


def test_quick_edit_has_no_named_project_folder_and_survives_restart(repo):
    workspaces = Workspaces(repo)
    project = workspaces.create_others()
    assert logical_path(project.path).is_relative_to(repo / "runtime/others")
    assert not list((repo / "projects").glob("*/project.yaml"))
    fresh = Workspaces(repo)
    assert fresh.list()[0]["category"] == "others"
    assert Project.open(repo, project.path.name).state()["validation_policy"] == "presentation"
    assert (repo / "output/Others").is_dir()
    assert "Never overwrite the supplied original PPTX" in project.path.joinpath("AGENTS.md").read_text(encoding="utf-8")


def test_explicit_quick_namespace_preserves_regular_project_routes(repo):
    ordinary = Project.create(repo, "others-ordinary", validation_policy="kernel")
    assert logical_path(ordinary.path) == repo / "projects/others-ordinary"
    with pytest.raises(StudioError):
        Project.create(repo, "not-a-quick-id", others=True)
    assert Project.open(repo, ordinary.path.name).path == ordinary.path


def test_noninteractive_quick_command_does_not_reuse_named_project(repo, capsys):
    workspaces = Workspaces(repo)
    named = workspaces.create("Named work")
    assert main(["--root", str(repo), "project", "quick"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["category"] == "others" and result["project_id"] != named.path.name
    assert Path(result["path"]).is_relative_to(repo / "runtime/others")
    assert len([row for row in workspaces.list() if row["category"] == "project"]) == 1


def test_export_updates_one_owned_copy_after_validated_revisions(repo):
    workspaces, project = kernel_quick(repo)
    commit(project, b"first validated fixture")
    first = export_others(repo, project.path.name)
    destination = Path(first["path"])
    assert destination.parent == repo / "output/Others" and first["generation"] == 1
    before = fingerprint(destination)
    assert export_others(repo, project.path.name) == first and fingerprint(destination) == before
    commit(project, b"second validated fixture")
    second = export_others(repo, project.path.name)
    assert first["path"] == second["path"] and second["generation"] == 2
    assert destination.read_bytes() == b"second validated fixture"
    assert workspaces.metadata(project)["export"] == second


@pytest.mark.parametrize("damage", ["canonical", "export"])
def test_external_edits_block_export_without_overwriting_user_bytes(repo, damage):
    _workspaces, project = kernel_quick(repo)
    commit(project, b"validated")
    record = export_others(repo, project.path.name)
    destination = Path(record["path"])
    affected = project.canonical if damage == "canonical" else destination
    affected.write_bytes(b"external user edits")
    with pytest.raises(StudioError) as exc:
        export_others(repo, project.path.name)
    assert exc.value.code == ErrorCode.FILE_CONFLICT
    assert affected.read_bytes() == b"external user edits"


def test_forged_output_path_and_other_task_owner_are_rejected(repo):
    workspaces, project = kernel_quick(repo)
    commit(project, b"validated")
    export_others(repo, project.path.name)
    metadata = workspaces.metadata(project)
    metadata["export"]["path"] = str(repo / "outside.pptx")
    workspaces.save(project, metadata)
    with pytest.raises(StudioError) as exc:
        export_others(repo, project.path.name)
    assert exc.value.code == ErrorCode.SECURITY_BLOCK
    metadata["export"]["path"] = str(repo / "output/Others/other-task_12345678.pptx")
    workspaces.save(project, metadata)
    with pytest.raises(StudioError) as exc:
        export_others(repo, project.path.name)
    assert exc.value.code == ErrorCode.SECURITY_BLOCK


def test_failed_commit_and_unsaved_live_authority_do_not_export(repo):
    workspaces, project = kernel_quick(repo)
    transaction = project.begin()
    project.candidate(transaction).write_bytes(b"rejected")
    with pytest.raises(StudioError):
        project.commit(transaction, lambda _path: {"passed": False, "errors": ["QA failure"]})
    assert export_others(repo, project.path.name) is None
    assert not list((repo / "output/Others").glob("*.pptx"))
    commit(project, b"validated")
    from state.io import write_yaml
    state = project.state()
    state["authority"] = "live"
    write_yaml(project.state_path, state)
    assert export_others(repo, project.path.name) is None
    assert "export" not in workspaces.metadata(project)


def test_output_junction_cannot_redirect_exports_or_quick_setup(repo):
    workspaces, project = kernel_quick(repo)
    commit(project, b"validated")
    outside = repo.parent / ("outside-output-" + uuid4().hex)
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"untouched")
    link = repo / "output/Others"
    link.parent.mkdir()
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=True)
    try:
        for action in [lambda: export_others(repo, project.path.name), workspaces.create_others]:
            with pytest.raises(StudioError) as exc:
                action()
            assert exc.value.code == ErrorCode.SECURITY_BLOCK
        assert marker.read_bytes() == b"untouched" and not list(outside.glob("*.pptx"))
    finally:
        link.rmdir()  # Remove only the junction, never recurse into its target.


def test_direct_prompt_routes_to_others_and_passes_human_request(repo):
    answers = iter(["Tolong edit PPT urgent", "q"])
    calls = []
    menu = ProjectMenu(repo, reader=lambda _prompt: next(answers), writer=lambda _text: None,
                       launcher=lambda ws, project, **options: calls.append((ws.metadata(project)["category"], options)) or 0)
    assert menu.run() == 0
    assert calls == [("others", {"resume": False, "prompt": "Tolong edit PPT urgent"})]
    assert not list((repo / "projects").glob("*/project.yaml"))


def test_others_group_can_reopen_a_saved_quick_edit(repo):
    workspaces = Workspaces(repo)
    project = workspaces.create_others()
    answers = iter(["o", "1", "q"])
    menu = ProjectMenu(repo, reader=lambda _prompt: next(answers), writer=lambda _text: None)
    assert menu.run() == 0 and workspaces.active() == project.path.name
    assert len(workspaces.list()) == 1


def test_codex_quick_prompt_and_output_permission_are_scoped(repo):
    project = Workspaces(repo).create_others()
    arguments = codex_launcher.command(repo, project, Path("codex.exe"), prompt="edit this PPT")
    assert str(repo / "output/Others") in arguments and arguments[-1] == "edit this PPT"
    assert str(repo / "projects") not in arguments
    with pytest.raises(StudioError):
        codex_launcher.command(repo, project, Path("codex.cmd"), prompt="a & b")


def test_native_quick_import_revision_and_separate_tasks_keep_original_unchanged(repo, capsys, monkeypatch):
    from layout.baseline import BaselineLayout
    from presentation.backends.ooxml import OOXMLBackend
    from presentation.compiler.compiler import PresentationCompiler
    import presentation.rendering.native as rendering
    workspaces = Workspaces(repo)
    project = workspaces.create_others()
    spec = read_json(ROOT / "tests/fixtures/basic_spec.json")
    source = repo / "runtime/Urgent deck.pptx"
    backend = OOXMLBackend(ROOT)
    PresentationCompiler(ROOT, BaselineLayout(ROOT), backend).compile(spec["brief"], spec["deck"], spec["slides"], source)
    before = fingerprint(source)
    native_renderer = rendering.NativeRenderer(ROOT)
    monkeypatch.setattr(rendering, "NativeRenderer", lambda _root: native_renderer)
    base = ["--root", str(repo)]
    assert main(base + ["project", "import", project.path.name, "--role", "target", "--source", str(source)]) == 0
    capsys.readouterr()
    first_output = workspaces.metadata(project)["export"]
    assert sha256(Path(first_output["path"])) == before["sha256"]
    inspection = backend.inspect(project.canonical)
    slide, obj = inspection["slides"][0], inspection["slides"][0]["objects"][0]
    patch = {"schema_version": "1.0", "patch_id": "urgent-revision", "operations": [{"slide_id": slide["slide_id"], "object_id": obj["object_id"], "operation": "set_text", "expected_fingerprint": obj["fingerprint"], "value": "An urgent revision preserves the original deck"}]}
    scope = {"objects": [{"slide_id": s["slide_id"], "object_id": o["object_id"], "protection": "MUST_CHANGE" if o["object_id"] == obj["object_id"] else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
    write_json(repo / "runtime/patch.json", patch)
    write_json(repo / "runtime/scope.json", scope)
    assert main(base + ["revise", project.path.name, "--patch", str(repo / "runtime/patch.json"), "--scope", str(repo / "runtime/scope.json")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["qa"]["passed"] and result["project"]["generation"] == 2
    final_output = workspaces.metadata(project)["export"]
    assert final_output["path"] == first_output["path"] and final_output["sha256"] != before["sha256"]
    assert backend.inspect(Path(final_output["path"]))["slides"][1] == inspection["slides"][1]
    other = workspaces.create_others()
    assert main(base + ["project", "import", other.path.name, "--role", "target", "--source", str(source)]) == 0
    capsys.readouterr()
    other_output = workspaces.metadata(other)["export"]
    assert final_output["path"] != other_output["path"] and fingerprint(source) == before
    assert sha256(Path(final_output["path"])) == final_output["sha256"]
    write_json(ROOT / "implementation/PHASE_REPORTS/others_native.json", {"passed": True, "renderer": "WindowsPowerPoint", "original": str(source), "original_sha256": before["sha256"], "revised_output": final_output, "second_output": other_output, "qa": result["qa"], "working_project": str(logical_path(project.path))})
