import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pptx import Presentation

from cli import codex_launcher
from cli.main import main
from cli.workspace_menu import ProjectMenu, pick_files
from state.errors import ErrorCode, StudioError
from state.intake import ProjectIntake
from state.io import fingerprint, logical_path, read_json, sha256, write_json
from state.project import Project
from state.workspace import CONTEXT_MARKER, Workspaces


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def managed(repo, project):
    workspaces = Workspaces(repo)
    workspaces.select(project.path.name)
    return workspaces, project, ProjectIntake(workspaces, project)


def source_file(repo, name="sales.csv", content="year,revenue\n2025,120\n"):
    path = repo / "external" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def target_file(repo, name="original.pptx"):
    path = repo / "external" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    deck = Presentation()
    deck.slides.add_slide(deck.slide_layouts[6])
    deck.save(path)
    return path


def test_named_project_survives_restart_without_fake_working_deck(repo):
    workspaces = Workspaces(repo)
    project = workspaces.create("2026 — Café 上海")
    fresh = Workspaces(repo)
    row = fresh.list()[0]
    assert row["name"] == "2026 — Café 上海"
    assert row["project_id"].startswith("project-2026-cafe-")
    assert fresh.active() == project.path.name
    assert not row["deck_exists"] and project.state()["validation_policy"] == "presentation"
    assert project.state()["generation"] == 0
    assert project.path.joinpath("AGENTS.md").read_text(encoding="utf-8").startswith(CONTEXT_MARKER)
    second = fresh.create(row["name"])
    assert second.path.name != project.path.name and len(fresh.list()) == 2


@pytest.mark.parametrize("name", ["", "   ", "bad\nname", "x" * 121])
def test_invalid_name_has_no_partial_project(repo, name):
    with pytest.raises(StudioError):
        Workspaces(repo).create(name)
    assert not list((repo / "projects").glob("*/project.yaml"))


def test_adoption_preserves_existing_state_and_custom_agent_instructions(repo, project):
    before = project.state_path.read_bytes()
    agents = project.path / "AGENTS.md"
    agents.write_text("Custom rules already in use", encoding="utf-8")
    workspaces = Workspaces(repo)
    workspaces.select(project.path.name)
    assert project.state_path.read_bytes() == before
    assert agents.read_text(encoding="utf-8") == "Custom rules already in use"
    args = codex_launcher.command(repo, project, Path("codex.exe"))
    assert "state/operator_context.md" in args[-1]


def test_synthetic_projects_hidden_until_explicitly_adopted(repo):
    fixture = Project.create(repo, "reason-smoke-12345678", validation_policy="kernel")
    workspaces = Workspaces(repo)
    assert workspaces.list() == [] and len(workspaces.list(True)) == 1
    workspaces.select(fixture.path.name)
    assert len(workspaces.list()) == 1


def test_import_copies_external_source_and_records_exact_provenance(managed, repo):
    workspaces, project, intake = managed
    source = source_file(repo)
    original = fingerprint(source)
    item = intake.import_path(source)[0]
    copy = Path(item["path"])
    assert copy.read_bytes() == source.read_bytes()
    assert copy.is_relative_to(logical_path(project.path / "input/sources"))
    provenance = read_json(copy.with_name(copy.name + ".source.json"))
    assert logical_path(Path(provenance["original_path"])) == source
    assert provenance["sha256"] == item["sha256"] and provenance["trust"] == "untrusted_data"
    assert not provenance["executable"] and fingerprint(source) == original
    assert ProjectIntake(Workspaces(repo), Project.open(repo, project.path.name)).files()[0]["verified"]
    with pytest.raises(StudioError):
        project.policy.check(copy, write=True)


def test_folder_preserves_relative_paths_and_versions_without_duplicate_entries(managed, repo):
    workspaces, project, intake = managed
    one = source_file(repo, "materials/one/data.csv")
    two = source_file(repo, "materials/two/data.csv", "year,revenue\n2025,240\n")
    notes = source_file(repo, "materials/README.md", "[one](one/data.csv) [two](two/data.csv)")
    folder = repo / "external/materials"
    items = intake.import_path(folder)
    copies = {Path(item["path"]).relative_to(Path(items[0]["path"]).parent).as_posix() for item in items}
    assert copies == {"README.md", "one/data.csv", "two/data.csv"}
    managed_notes = next(Path(item["path"]) for item in items if Path(item["path"]).name == "README.md")
    assert managed_notes.read_bytes() == notes.read_bytes()
    old = [(Path(item["path"]), sha256(Path(item["path"]))) for item in items]
    intake.import_path(folder)
    assert len(workspaces.metadata(project)["imports"]) == 3
    one.write_text("year,revenue\n2025,999\n", encoding="utf-8")
    new = intake.import_path(folder)
    assert len(workspaces.metadata(project)["imports"]) == 6
    assert {item["path"] for item in new}.isdisjoint({item["path"] for item in items})
    assert all(sha256(path) == digest for path, digest in old)
    assert two.exists()


def test_all_folder_files_validated_before_materialization(managed, repo):
    _, project, intake = managed
    source_file(repo, "mixed/good.txt", "valid text")
    source_file(repo, "mixed/program.exe", "untrusted executable")
    with pytest.raises(StudioError) as exc:
        intake.import_path(repo / "external/mixed")
    assert exc.value.code == ErrorCode.SECURITY_BLOCK
    assert intake.files() == [] and not list((project.path / "input/sources").rglob("*.txt"))


def test_multiple_picked_files_preserve_links_in_one_idempotent_batch(managed, repo):
    _, _, intake = managed
    notes = source_file(repo, "bundle/README.md", "[data](nested/data.csv)")
    data = source_file(repo, "bundle/nested/data.csv")
    items = intake.import_paths([notes, data])
    managed_notes = next(Path(item["path"]) for item in items if Path(item["path"]).name == "README.md")
    assert (managed_notes.parent / "nested/data.csv").read_bytes() == data.read_bytes()
    intake.import_paths([data, notes, data])
    assert len(intake.files()) == 2


def test_managed_folder_cannot_be_recursively_reimported(managed, repo):
    _, project, intake = managed
    intake.import_path(source_file(repo))
    with pytest.raises(StudioError) as exc:
        intake.import_path(project.path / "input/sources")
    assert exc.value.code == ErrorCode.FILE_CONFLICT


def test_sidecar_name_conflicts_do_not_corrupt_internal_files(managed, repo):
    _, _, intake = managed
    source_file(repo, "mixed/data.txt", "text")
    source_file(repo, "mixed/data.txt.source.json", "{}")
    with pytest.raises(StudioError) as exc:
        intake.import_path(repo / "external/mixed")
    assert exc.value.code == ErrorCode.FILE_CONFLICT and intake.files() == []


def test_zip_paths_checked_without_extracting_or_following_links(managed, repo):
    _, _, intake = managed
    archive = repo / "bad.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape.txt", "bad")
    with pytest.raises(StudioError) as exc:
        intake.import_path(archive)
    assert exc.value.code == ErrorCode.SECURITY_BLOCK and intake.files() == []


def test_cannot_recursively_import_destination_project(managed, repo):
    with pytest.raises(StudioError) as exc:
        managed[2].import_path(repo)
    assert exc.value.code == ErrorCode.SECURITY_BLOCK


@pytest.mark.parametrize("damage", ["changed", "missing"])
def test_damaged_input_blocks_codex_launch_before_invocation(managed, repo, monkeypatch, damage):
    workspaces, project, intake = managed
    item = intake.import_path(source_file(repo))[0]
    copy = Path(item["path"])
    if damage == "missing":
        copy.unlink()
    else:
        copy.write_text("changed", encoding="utf-8")
    monkeypatch.setattr(codex_launcher, "resolve_codex", lambda: Path("codex.exe"))
    with pytest.raises(StudioError) as exc:
        codex_launcher.launch(workspaces, project, runner=lambda *_args, **_kwargs: pytest.fail("Must not launch"))
    assert exc.value.code == ErrorCode.SOURCE_CONFLICT


def test_inventory_cannot_redirect_to_an_external_file(managed, repo):
    workspaces, project, intake = managed
    source = source_file(repo)
    intake.import_path(source)
    data = workspaces.metadata(project)
    data["imports"][0]["path"] = str(source)
    workspaces.save(project, data)
    with pytest.raises(StudioError) as exc:
        intake.files()
    assert exc.value.code == ErrorCode.SECURITY_BLOCK


def test_initial_target_uses_transaction_and_refuses_second_working_deck(managed, repo):
    _, project, intake = managed
    source = target_file(repo)
    before = fingerprint(source)
    item = intake.import_path(source, "target")[0]
    validator = lambda _path: {"passed": True, "errors": []}
    assert intake.initialize_target(item, validator)["generation"] == 1
    canonical = fingerprint(project.canonical)
    assert sha256(project.canonical) == item["sha256"] and fingerprint(source) == before
    assert intake.initialize_target(item, validator)["generation"] == 1
    different = target_file(repo, "different.pptx")
    deck = Presentation(different)
    deck.slides.add_slide(deck.slide_layouts[6])
    deck.save(different)
    other = intake.import_path(different, "target")[0]
    with pytest.raises(StudioError) as exc:
        intake.initialize_target(other, validator)
    assert exc.value.code == ErrorCode.FILE_CONFLICT and fingerprint(project.canonical) == canonical


def test_failed_target_validation_retains_input_but_never_creates_canonical(managed, repo):
    _, project, intake = managed
    item = intake.import_path(target_file(repo), "target")[0]
    with pytest.raises(StudioError):
        intake.initialize_target(item, lambda _path: {"passed": False, "errors": ["invalid"]})
    assert not project.canonical.exists() and project.state()["generation"] == 0
    assert intake.files()[0]["verified"]
    journal = next((project.path / "work/transactions").glob("*/transaction.json"))
    assert read_json(journal)["status"] == "aborted"


def test_target_import_race_cannot_replace_an_intervening_deck(managed, repo, monkeypatch):
    _, project, intake = managed
    item = intake.import_path(target_file(repo), "target")[0]
    begin = project.begin
    def raced_begin():
        intervening = begin()
        project.candidate(intervening).write_bytes(b"valid: user deck")
        project.commit(intervening, lambda _path: {"passed": True, "errors": []})
        return begin()
    monkeypatch.setattr(project, "begin", raced_begin)
    with pytest.raises(StudioError) as exc:
        intake.initialize_target(item, lambda _path: {"passed": True, "errors": []})
    assert exc.value.code == ErrorCode.FILE_CONFLICT
    assert project.canonical.read_bytes() == b"valid: user deck"


def test_launcher_is_scoped_and_reuses_user_configuration(managed, repo, monkeypatch):
    workspaces, project, intake = managed
    intake.import_path(source_file(repo))
    executable = Path("C:/apps/Codex/codex.exe")
    monkeypatch.setattr(codex_launcher, "resolve_codex", lambda: executable)
    calls = []
    def runner(args, **options):
        calls.append((args, options))
        return SimpleNamespace(returncode=0)
    assert codex_launcher.launch(workspaces, project, resume=True, runner=runner) == 0
    args, options = calls[0]
    assert "--no-daemon" in args and args[-2:] == ["resume", "--last"]
    assert "--all" not in args and "--model" not in args and "-m" not in args
    assert str(repo / "projects") not in args
    assert options["cwd"] == logical_path(project.path)
    assert options["env"]["PATH"].startswith(str(executable.parent))
    assert workspaces.metadata(project)["last_chat_started_at"]
    assert workspaces.metadata(project)["last_chat_exit_code"] == 0


def test_terminal_menu_create_import_chat_and_reopen(managed, repo):
    _, original, _ = managed
    source = source_file(repo)
    output, calls = [], []
    answers = iter(["n", "Board meeting", "3", "1", "b", "n", "Other deck", "q"])
    menu = ProjectMenu(repo, reader=lambda _prompt: next(answers), writer=output.append, picker=lambda **_kwargs: [source], launcher=lambda ws, project, resume: calls.append((project.path.name, resume)) or 0)
    assert menu.run() == 0
    fresh = Workspaces(repo)
    rows = fresh.list()
    assert len(rows) == 3 and calls[0][1] is False
    assert next(row for row in rows if row["name"] == "Board meeting")["file_count"] == 1
    assert fresh.active() != original.path.name
    choices = iter(["1", "2", "q"])
    reopened = ProjectMenu(repo, reader=lambda _prompt: next(choices), writer=output.append, launcher=lambda ws, project, resume: calls.append((project.path.name, resume)) or 0)
    assert reopened.run() == 0 and calls[-1] == (fresh.active(), True)


def test_start_menu_routes_to_codex_knowledge_and_project_import(repo, monkeypatch):
    from knowledge.store import KnowledgeStore

    ingested = []
    monkeypatch.setattr(KnowledgeStore, "ingest", lambda self, package_id: ingested.append(package_id) or {"status": "unchanged", "files": 1124, "chunks": 53})
    output = []
    knowledge_answers = iter(["2", "q"])
    knowledge_menu = ProjectMenu(repo, reader=lambda _prompt: next(knowledge_answers), writer=output.append)
    assert knowledge_menu.start_menu() == 0
    assert ingested == ["consulting_deck_knowledge_v1"]
    assert any("sudah terbaru" in line for line in output)

    workspaces = Workspaces(repo)
    project = workspaces.create("Research project")
    source = repo / "external" / "research.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    import fitz
    document = fitz.open()
    document.new_page().insert_text((72, 72), "A supporting PDF source")
    document.save(source)
    document.close()
    answers = iter(["3", "1", "1", "q"])
    import_menu = ProjectMenu(repo, reader=lambda _prompt: next(answers), writer=output.append, picker=lambda **_kwargs: [source])
    assert import_menu.start_menu() == 0
    imported = ProjectIntake(workspaces, project).files()
    assert len(imported) == 1 and imported[0]["role"] == "source" and imported[0]["verified"]


def test_cli_no_arguments_opens_start_activity_menu(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(ProjectMenu, "start_menu", lambda self: calls.append(self.workspaces.root) or 0)
    assert main(["--root", str(repo)]) == 0
    assert calls == [repo]


def test_cli_import_and_listing_do_not_change_other_projects_active_selection(managed, repo, capsys):
    workspaces, project, intake = managed
    other = workspaces.create("Other")
    source = source_file(repo)
    args = ["--root", str(repo), "project"]
    assert main(args + ["import", project.path.name, "--source", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["files"]) == 1 and intake.files()[0]["verified"]
    assert workspaces.active() == other.path.name
    assert main(args + ["use", project.path.name]) == 0
    capsys.readouterr()
    assert workspaces.active() == project.path.name
    assert main(args + ["files"]) == 0
    assert json.loads(capsys.readouterr().out)["files"][0]["verified"]
    assert main(args + ["list"]) == 0
    assert len(json.loads(capsys.readouterr().out)["projects"]) == 2


def test_file_picker_unavailable_has_actionable_cli_fallback(monkeypatch):
    import tkinter
    monkeypatch.setattr(tkinter, "Tk", lambda: (_ for _ in ()).throw(tkinter.TclError("No window")))
    with pytest.raises(StudioError) as exc:
        pick_files()
    assert exc.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "--source" in str(exc.value)


def test_production_target_import_requires_real_native_qa(repo):
    from layout.baseline import BaselineLayout
    from presentation.backends.ooxml import OOXMLBackend
    from presentation.compiler.compiler import PresentationCompiler
    from presentation.rendering.native import NativeRenderer
    from qa.transaction import PresentationValidator
    workspaces = Workspaces(repo)
    project = workspaces.create("Native target proof")
    intake = ProjectIntake(workspaces, project)
    source = repo / "runtime/starting.pptx"
    spec = read_json(ROOT / "tests/fixtures/basic_spec.json")
    backend = OOXMLBackend(ROOT)
    PresentationCompiler(ROOT, BaselineLayout(ROOT), backend).compile(spec["brief"], spec["deck"], spec["slides"], source)
    before = fingerprint(source)
    item = intake.import_path(source, "target")[0]
    # The isolated project remains subject to the normal production commit gate.
    with pytest.raises(StudioError):
        intake.initialize_target(item, backend.validate)
    assert not project.canonical.exists()
    validator = PresentationValidator(ROOT, backend, NativeRenderer(ROOT), project.path / "output/qa/target_import")
    state = intake.initialize_target(item, validator)
    assert state["generation"] == 1 and fingerprint(source) == before
    proof = read_json(project.path / "output/qa/target_import/render_report.json")
    assert proof["passed"] and proof["renderer"] == "WindowsPowerPoint"
    assert proof["input_sha256"] == sha256(project.canonical) == item["sha256"]

