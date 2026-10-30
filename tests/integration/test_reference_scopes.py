"""Scope, provenance and approval controls; synthetic previews are not native QA."""
import importlib.util
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from cli.main import main
from cli.workspace_menu import ProjectMenu
from layout.baseline import BaselineLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from presentation.compiler.design import DesignPlanner
from presentation.rendering.native import NativeRenderer
from references.catalog import DatabaseIntake, ReferenceCatalog
from references.migration import consolidate_unindexed
from references.store import ReferenceStore
from state.errors import ErrorCode, StudioError
from state.intake import ProjectIntake
from state.io import fingerprint, logical_path, native_path, read_json, sha256, write_json
from state.workspace import Workspaces

ROOT=Path(__file__).resolve().parents[2]


def fixture_module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tests/integration"/(name+".py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


FixtureRenderer=fixture_module("test_reference_store").FixtureRenderer


def deck(root,name="precedent",title=None):
    spec=deepcopy(read_json(ROOT/"tests/fixtures/basic_spec.json"))
    if title:spec["slides"][0]["action_title"]=title
    path=root/"runtime"/(name+".pptx")
    PresentationCompiler(root,BaselineLayout(root),OOXMLBackend(root)).compile(**spec,destination=path)
    return path


@pytest.fixture
def scoped(repo):
    ws=Workspaces(repo);a=ws.create("Business A");b=ws.create("Business B")
    catalogs=[ReferenceCatalog(repo,renderer=FixtureRenderer(repo)),ReferenceCatalog(repo,project_id=a.path.name,renderer=FixtureRenderer(repo)),ReferenceCatalog(repo,project_id=b.path.name,renderer=FixtureRenderer(repo))]
    for catalog,scope,name in zip(catalogs,["database","project","project"],["General","Private A","Private B"],strict=True):
        catalog.import_paths([deck(repo,name,name+" precedents support the decision")],scope=scope)
        assert catalog.store(scope).ingest()["passed"]
    return ws,a,b,catalogs


@pytest.mark.parametrize("stage",["metadata","preview","structure","original"])
def test_general_and_one_explicit_project_only_at_every_load_stage(scoped,stage):
    ws,a,b,(general,ca,cb)=scoped
    assert ws.active()==b.path.name
    global_rows=general.query({"text":"decision"},20)
    a_rows=ca.query({"text":"decision"},20);b_rows=cb.query({"text":"decision"},20)
    assert len(global_rows)==2 and len(a_rows)==len(b_rows)==4
    assert {row["scope"] for row in global_rows}=={"database"}
    private_a=next(row for row in a_rows if row["scope"]=="project")
    assert not any(row["reference_id"]==private_a["reference_id"] for row in b_rows)
    assert ca.load(private_a["reference_id"],private_a["slide_id"],stage,scope="project")["project_id"]==a.path.name
    for catalog in [general,cb]:
        with pytest.raises(StudioError):catalog.load(private_a["reference_id"],private_a["slide_id"],stage,scope="project")


def test_same_ppt_in_different_scopes_does_not_merge_private_identity(repo):
    ws=Workspaces(repo);a=ws.create("A");b=ws.create("B");original=deck(repo)
    ids=[]
    for project in [a,b]:
        catalog=ReferenceCatalog(repo,project_id=project.path.name,renderer=FixtureRenderer(repo))
        catalog.import_paths([original],scope="project");assert catalog.store("project").ingest()["passed"]
        ids.append(catalog.store("project").query({"text":"decision"})[0]["reference_id"])
    assert ids[0]!=ids[1] and ReferenceCatalog(repo).query({"text":"decision"})==[]


def test_approval_stays_in_database_and_changes_invalidate_it(repo):
    catalog=ReferenceCatalog(repo,renderer=FixtureRenderer(repo));original=deck(repo)
    imported=catalog.import_paths([original])[0];store=catalog.store("database");store.ingest()
    # This case edits the first slide below. Ranking ties depend on path-based
    # IDs, so approve that slide explicitly rather than an arbitrary top hit.
    indexed=next(iter(store.state()['decks'].values()))
    target_slide=indexed['slides'][0]['slide_id']
    row=next(row for row in store.query({"text":"decision"}) if row['slide_id']==target_slide)
    before=fingerprint(original)
    store.promote(row["reference_id"],row["slide_id"],reason="Explicit reviewed precedent")
    assert store.load(row["reference_id"],row["slide_id"])["approval"]=="approved"
    for stage in ["original","preview"]:
        path=store.load(row["reference_id"],row["slide_id"],stage)["path"]
        assert "database" in path and "approved_internal" not in path
    assert store.promote(row["reference_id"],row["slide_id"],reason="Again")["status"]=="unchanged"
    # Simulate a source change to exercise the existing incremental trust gate.
    changed=deck(repo,"changed","A revised reference invalidates its old approval")
    native_path(Path(imported["path"])).write_bytes(changed.read_bytes())
    assert store.ingest()["rendered_slides"]==1
    first=store.state()["decks"][row["reference_id"]]["slides"][0]
    assert first["approval"]=="unreviewed" and first["approval_history"][-1]["status"]=="deprecated"
    assert fingerprint(original)==before


def test_documents_and_folder_links_preserve_provenance_without_creating_working_ppt(repo):
    ws=Workspaces(repo);project=ws.create("Business documents")
    folder=repo/"materials";(folder/"data").mkdir(parents=True)
    (folder/"index.md").write_text("[sales](data/sales.csv)",encoding="utf-8")
    (folder/"data/sales.csv").write_text("year,revenue\n2025,12\n",encoding="utf-8")
    originals={p.relative_to(folder):sha256(p) for p in folder.rglob("*") if p.is_file()}
    intake=ProjectIntake(ws,project);rows=intake.import_paths([folder],"reference")
    for row in rows:
        path=native_path(Path(row["path"]));assert sha256(path)==originals[native_path(Path(row["original_path"])).relative_to(native_path(folder))]
    index=native_path(Path(next(row["path"] for row in rows if row["path"].endswith("index.md"))))
    assert (index.parent/"data/sales.csv").is_file()
    assert all(row["verified"] for row in intake.files()) and not project.canonical.exists()
    with pytest.raises(StudioError):project.policy.check(index,write=True)
    report=ReferenceStore(repo,FixtureRenderer(repo),project_id=project.path.name).ingest()
    assert report["passed"] and report["items"]==[]
    assert len(ReferenceCatalog(repo,project_id=project.path.name).files())==2
    assert ReferenceCatalog(repo).files()==[]


def test_others_has_general_references_and_cannot_claim_named_project_scope(repo):
    ws=Workspaces(repo);quick=ws.create_others()
    assert ReferenceCatalog(repo).query({"text":"decision"})==[]
    with pytest.raises(StudioError) as error:ReferenceCatalog(repo,project_id=quick.path.name)
    assert error.value.code==ErrorCode.SECURITY_BLOCK
    with pytest.raises(StudioError):ProjectIntake(ws,quick).import_paths([deck(repo)],"reference")
    context=(quick.path/"state/operator_context.md").read_text(encoding="utf-8")
    assert "including Others" in context and "--use-project-references" not in context


@pytest.mark.parametrize("stage",["metadata","preview","structure","original"])
def test_forged_project_manifest_cannot_read_another_scope(scoped,stage):
    _,a,b,(_,ca,cb)=scoped
    row=next(row for row in cb.query({"text":"decision"}) if row["scope"]=="project")
    store=ca.store("project");value=store.state()
    foreign=cb.store("project").state()["decks"][row["reference_id"]]
    value["decks"][row["reference_id"]]=foreign;write_json(store.manifest,value)
    with pytest.raises(StudioError) as error:store.load(row["reference_id"],row["slide_id"],stage)
    assert error.value.code==ErrorCode.SECURITY_BLOCK


def test_cli_defaults_to_general_even_when_private_project_is_active(scoped,repo,capsys):
    ws,a,b,(_,ca,_)=scoped
    base=["--root",str(repo),"references"]
    assert main(base+["query","decision"])==0
    rows=json.loads(capsys.readouterr().out);assert len(rows)==2 and all(row["scope"]=="database" for row in rows)
    assert main(base+["query","decision","--project",a.path.name])==0
    rows=json.loads(capsys.readouterr().out);assert len(rows)==4 and {row["project_id"] for row in rows}=={None,a.path.name}
    assert main(base+["files","--scope","project"])==1
    assert json.loads(capsys.readouterr().out)["code"]=="SECURITY_BLOCK"
    assert ws.active()==b.path.name


def test_migration_preserves_bytes_internal_paths_origins_exclusions_and_replay(repo):
    base=repo/"library/references";old=base/"approved_internal/originals/nested";old.mkdir(parents=True)
    original=deck(repo);source=old/"user.pptx";source.write_bytes(original.read_bytes())
    fixture=base/"external/originals/fixture.pptx";fixture.parent.mkdir(parents=True);fixture.write_bytes(original.read_bytes())
    write_json(base/"manifests/library.json",{"schema_version":"1.0","pipeline_version":"1.0","decks":{},"aliases":{},"excluded_sources":[str(logical_path(fixture))]})
    before=sha256(source);report=consolidate_unindexed(repo)
    target=base/"database/originals/nested/user.pptx"
    assert report["status"]=="complete" and sha256(target)==before and not source.exists()
    assert not (base/"external").exists() and not (base/"approved_internal").exists()
    assert consolidate_unindexed(repo)["rows"]==report["rows"]
    files=DatabaseIntake(repo).files();assert len(files)==1 and files[0]["original_path"]==str(logical_path(source)) and files[0]["verified"]
    candidates=ReferenceStore(repo).ingest(dry_run=True)["items"]
    assert len(candidates)==1 and candidates[0]["source_path"]==str(logical_path(target))
    assert ReferenceStore(repo,FixtureRenderer(repo)).ingest()["passed"]
    assert consolidate_unindexed(repo)["rows"]==report["rows"]


def test_migration_stops_on_collisions_without_moving_any_source(repo):
    base=repo/"library/references"
    for library in ["external","approved_internal"]:
        folder=base/library/"originals";folder.mkdir(parents=True);(folder/"same.txt").write_text(library)
    with pytest.raises(StudioError):consolidate_unindexed(repo)
    assert len(list(base.glob("*/originals/same.txt")))==2


def test_picker_database_and_business_references_survive_restart(repo):
    source=repo/"runtime/brief.md";source.write_text("Business reference",encoding="utf-8")
    answers=iter(["d","1","b","n","My business","r","1","b","q"])
    output=[]
    menu=ProjectMenu(repo,reader=lambda _:next(answers),writer=output.append,picker=lambda **_: [source])
    assert menu.run()==0
    ws=Workspaces(repo);project=ws.list()[0]["project_id"]
    files=ReferenceCatalog(repo,project_id=project).files()
    assert {row["scope"] for row in files}=={"database","project"} and all(row["verified"] for row in files)
    assert any("[D] Database" in row for row in output) and any("[R] References" in row for row in output)


def test_design_records_only_explicit_scope_and_never_imports_reference_facts(scoped,repo):
    ws,a,b,(general,ca,cb)=scoped
    request,store,intent=fixture_module("test_design_planning").prepare(repo,a)
    planner=DesignPlanner(repo,a)
    general_spec=planner.plan(request["brief"],{"a1":intent})
    candidates=read_json(a.path/"state/reference_candidates.json")
    assert candidates["project_scope"] is None
    assert all(row["scope"]=="database" for slide in candidates["slides"] for row in slide["candidates"])
    evidence_before=store.load().value
    scoped_spec=planner.plan(request["brief"],{"a1":intent},reference_project=a.path.name)
    candidates=read_json(a.path/"state/reference_candidates.json")
    assert candidates["project_scope"]==a.path.name and candidates["purpose"]=="design_precedents_only"
    assert {row["project_id"] for slide in candidates["slides"] for row in slide["candidates"]}=={None,a.path.name}
    assert scoped_spec==general_spec and store.load().value==evidence_before
    with pytest.raises(StudioError):planner.plan(request["brief"],reference_project=b.path.name)


def test_reference_originals_junction_cannot_import_or_ingest_other_project(repo):
    ws=Workspaces(repo);a=ws.create("A");b=ws.create("B")
    link=logical_path(a.path/"references/originals");link.rmdir()
    target=logical_path(b.path/"references/originals");marker=target/"keep.md";marker.write_text("untouched")
    subprocess.run(["cmd.exe","/c","mklink","/J",str(link),str(target)],capture_output=True,check=True)
    try:
        for action in [lambda:ProjectIntake(ws,a).import_paths([marker],"reference"),lambda:ReferenceStore(repo,project_id=a.path.name).ingest(dry_run=True)]:
            with pytest.raises(StudioError) as error:action()
            assert error.value.code==ErrorCode.SECURITY_BLOCK
        assert marker.read_text()=="untouched"
    finally:link.rmdir()


def test_real_native_unified_database_and_scoped_project(repo):
    original=deck(repo);before=fingerprint(original);ws=Workspaces(repo);project=ws.create("Native isolated business")
    catalog=ReferenceCatalog(repo,project_id=project.path.name,renderer=NativeRenderer(ROOT,90))
    for scope in ["database","project"]:
        catalog.import_paths([original],scope=scope)
        result=catalog.store(scope).ingest();assert result["passed"],result
    rows=catalog.query({"text":"decision"},20)
    assert len(rows)==4 and len(ReferenceCatalog(repo).query({"text":"decision"},20))==2
    row=next(row for row in rows if row["scope"]=="project")
    catalog.store("project").promote(row["reference_id"],row["slide_id"],reason="Native isolated approval",actor="integration_test")
    preview=catalog.load(row["reference_id"],row["slide_id"],"preview",scope="project")
    assert fingerprint(original)==before and native_path(Path(preview["path"])).is_file()
    assert catalog.load(row["reference_id"],row["slide_id"],scope="project")["visual"]["fonts"]
    write_json(ROOT/"implementation/PHASE_REPORTS/database_native.json",{"passed":True,"repository":str(repo),"project_id":project.path.name,"query_scopes":["database","project"],"source_preserved":True,"preview":preview,"approval_preserved":True})
