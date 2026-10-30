from copy import deepcopy
from pathlib import Path
import shutil

import pytest
from PIL import Image

from layout.baseline import BaselineLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from references.store import ReferenceStore
from state.errors import StudioError
from state.io import read_json,write_json,sha256,fingerprint,native_path


class FixtureRenderer:
    """Deterministic ingestion control fixture; never a native visual gate."""
    def __init__(self,root):self.root,self.calls=root,[]
    def render(self,source,output,slide_indices=None):
        self.calls.append(list(slide_indices));output.mkdir(parents=True)
        inspection=OOXMLBackend(self.root).inspect(source);slides=[]
        for number in slide_indices:
            path=output/f"slide_{number:03}.png";Image.new("RGB",(1600,900),"white").save(path)
            slides.append({"index":number,"native_slide_id":number,"render":str(path),"shapes":[]})
        return {"passed":True,"renderer":"ingestion_control_fixture","input_sha256":sha256(source),"slides":slides}


def create_reference(root,name="reference.pptx",spec=None):
    # Historical 1.0 behavior remains covered independently of unified defaults.
    from state.io import read_yaml,write_yaml
    config=read_yaml(root/"config/references/sources.yaml")
    config.update(schema_version="1.0",sources=[{"path":"library/references/approved_internal/originals","library":"approved_internal"},{"path":"library/references/external/originals","library":"external"}])
    write_yaml(root/"config/references/sources.yaml",config)
    spec=spec or read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json")
    output=root/"runtime"/name;PresentationCompiler(root,BaselineLayout(root),OOXMLBackend(root)).compile(**spec,destination=output)
    original=root/"library/references/external/originals"/name;original.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(output,original)
    return original,spec


def test_batch_dedup_dryrun_idempotency_and_progressive_loading(repo):
    original,spec=create_reference(repo)
    duplicate=original.with_name("duplicate.pptx");shutil.copy2(original,duplicate)
    other=deepcopy(spec);other["slides"][0]["action_title"]="A distinct reference changes the decision message";create_reference(repo,"other.pptx",other)
    before=fingerprint(original);renderer=FixtureRenderer(repo);store=ReferenceStore(repo,renderer)
    dry=store.ingest(dry_run=True);assert len(dry["items"])==3 and not renderer.calls and not store.manifest.exists()
    result=store.ingest();assert result["counts"]=={"new_ingested":2,"duplicate_skipped":1} and len(renderer.calls)==2
    again=store.ingest();assert again["counts"]=={"unchanged_skipped":2,"duplicate_skipped":1} and len(renderer.calls)==2
    assert fingerprint(original)==before
    candidate=store.query({"text":"decision"},limit=1)[0]
    metadata=store.load(candidate["reference_id"],candidate["slide_id"])
    assert "elements" not in metadata["structural"] and metadata["trust"]=="untrusted_reference_data"
    assert native_path(Path(store.load(candidate["reference_id"],candidate["slide_id"],"preview")["path"])).is_file()
    assert store.load(candidate["reference_id"],candidate["slide_id"],"structure")["element_graph"]["nodes"]
    assert store.load(candidate["reference_id"],candidate["slide_id"],"original")["sha256"]==store.state()["decks"][candidate["reference_id"]]["file_sha256"]


def test_changed_slide_incremental_approval_invalidation_and_removed_slide(repo):
    original,spec=create_reference(repo);renderer=FixtureRenderer(repo);store=ReferenceStore(repo,renderer)
    store.ingest();deck=next(iter(store.state()["decks"].values()));first=deck["slides"][0]
    store.promote(deck["reference_id"],first["slide_id"],reason="Approved controlled test pattern")
    assert store.query({"text":first["summary"]["title"]})[0]["approval"]=="approved"
    assert "approved_internal" in store.load(deck["reference_id"],first["slide_id"],"preview")["path"]
    assert "approved_internal" in store.load(deck["reference_id"],first["slide_id"],"original")["path"]
    changed=deepcopy(spec);changed["slides"][0]["action_title"]="A revised message changes only the first reference slide";create_reference(repo,spec=changed)
    result=store.ingest();assert result["rendered_slides"]==1 and result["reused_slides"]==1 and renderer.calls[-1]==[1]
    now=store.state()["decks"][deck["reference_id"]];assert now["slides"][0]["slide_id"]==first["slide_id"] and now["slides"][0]["approval"]=="unreviewed"
    changed["slides"]=changed["slides"][:1];changed["deck"]["slide_ids"]=changed["deck"]["slide_ids"][:1];create_reference(repo,spec=changed)
    result=store.ingest();assert result["rendered_slides"]==0 and result["reused_slides"]==1
    assert store.state()["decks"][deck["reference_id"]]["removed_slide_ids"]==[deck["slides"][1]["slide_id"]]


def test_failure_isolation_preserves_previous_index_and_force_recovers_derivatives(repo):
    original,spec=create_reference(repo);renderer=FixtureRenderer(repo);store=ReferenceStore(repo,renderer)
    store.ingest();previous=store.state()
    valid_bytes=original.read_bytes()
    original.write_bytes(b"corrupted PPTX")
    original.with_name("valid_new.pptx").write_bytes(valid_bytes)
    result=store.ingest();assert result["counts"]["failed"]==1 and result["counts"]["duplicate_skipped"]==1
    assert store.state()["decks"]==previous["decks"]
    original,spec=create_reference(repo,spec=spec)
    slide=next(iter(store.state()["decks"].values()))["slides"][0]
    native_path(Path(slide["artifacts"]["preview"]["path"])).write_bytes(b"tampered derivative")
    with pytest.raises(StudioError):store.load(next(iter(previous["decks"])),slide["slide_id"],"preview")
    assert store.ingest(force=True)["passed"]


def test_index_rebuild_without_original_loading_and_retrieval_ranking(repo):
    original,spec=create_reference(repo);store=ReferenceStore(repo,FixtureRenderer(repo));store.ingest()
    candidate=store.query({"text":"executive","content_shape":"text","brand":"unknown"})[0]
    state=store.state();deck=state["decks"][candidate["reference_id"]]
    snapshot=native_path(Path(deck["snapshot"]));content=snapshot.read_bytes();snapshot.write_bytes(b"corrupt original snapshot")
    store.index.unlink()
    assert store.query({"text":"executive"}) and store.load(candidate["reference_id"],candidate["slide_id"])
    with pytest.raises(StudioError):store.load(candidate["reference_id"],candidate["slide_id"],"original")
    snapshot.write_bytes(content)
    store.promote(candidate["reference_id"],candidate["slide_id"],reason="Explicit approval")
    ranked=store.query({"text":"","content_shape":"text"})
    assert ranked[0]["approval"]=="approved" and ranked[0]["library"]=="approved_internal"


def test_master_or_embedded_dependency_change_invalidates_slide_hash(repo):
    from references.fingerprints import slide_fingerprint
    from presentation.backends.xml import parse,serialize,NS
    original,spec=create_reference(repo);backend=OOXMLBackend(repo);package=backend._read(original);slide=backend.inspect(original)["slides"][0]
    before=slide_fingerprint(package,slide["part"]);name="ppt/slideMasters/slideMaster1.xml";master=parse(package[name][1]);master.set("preserve","1");package[name]=(package[name][0],serialize(master))
    assert slide_fingerprint(package,slide["part"])!=before


def test_changed_deck_becoming_duplicate_retires_only_old_index_rows(repo):
    first,spec=create_reference(repo,"a.pptx");changed=deepcopy(spec);changed["slides"][0]["action_title"]="A different reference supports the response decision";second,_=create_reference(repo,"b.pptx",changed)
    renderer=FixtureRenderer(repo);store=ReferenceStore(repo,renderer);store.ingest();before=store.state()
    first.write_bytes(second.read_bytes())
    result=store.ingest();assert result["counts"]=={"duplicate_skipped":1,"unchanged_skipped":1} and len(renderer.calls)==2
    state=store.state();assert sum(deck.get("active",True) for deck in state["decks"].values())==1
    assert len(store.query({"text":""},limit=20))==2
    retired=next(deck for deck in state["decks"].values() if not deck.get("active",True))
    assert store.load(retired["reference_id"],retired["slides"][0]["slide_id"],"original")["sha256"]==retired["file_sha256"]


def test_concurrent_source_edit_preserves_the_previous_valid_reference(repo):
    original,spec=create_reference(repo);store=ReferenceStore(repo,FixtureRenderer(repo));store.ingest();before=store.state();previous_bytes=original.read_bytes()
    changed=deepcopy(spec);changed["slides"][0]["action_title"]="A planned revision must not overwrite concurrent user work";create_reference(repo,spec=changed)
    class ConcurrentRenderer(FixtureRenderer):
        def render(self,*args,**kwargs):
            result=super().render(*args,**kwargs);original.write_bytes(previous_bytes);return result
    store.renderer=ConcurrentRenderer(repo)
    result=store.ingest()
    assert result["counts"]["failed"]==1 and result["items"][0]["error"]["code"]=="FILE_CONFLICT"
    assert store.state()["decks"]==before["decks"] and original.read_bytes()==previous_bytes


def test_configuration_cannot_escape_the_workspace(repo):
    from state.io import read_yaml,write_yaml
    configuration=read_yaml(repo/"config/references/sources.yaml");configuration["sources"][0]["path"]="../../outside-reference-root"
    write_yaml(repo/"config/references/sources.yaml",configuration)
    with pytest.raises(StudioError) as error:ReferenceStore(repo).ingest(dry_run=True)
    assert error.value.code.value=="SECURITY_BLOCK"


def test_ingestion_releases_raw_package_before_native_render(repo,monkeypatch):
    import weakref
    create_reference(repo)
    packages=[]
    class Package(dict):pass
    class MemoryGuardRenderer(FixtureRenderer):
        def render(self,*args,**kwargs):
            assert packages and all(reference() is None for reference in packages)
            return super().render(*args,**kwargs)
    store=ReferenceStore(repo,MemoryGuardRenderer(repo))
    original_read=store.backend._read
    def tracked_read(path):
        package=Package(original_read(path));packages.append(weakref.ref(package))
        return package
    monkeypatch.setattr(store.backend,'_read',tracked_read)
    result=store.ingest()
    assert result['passed'],result
    assert result['rendered_slides']==2
