"""Clone the proven synthetic Phase 9 artifact; preserve immutable source provenance.

The proof project was archived on 2026-10-24 (see docs/WORKSPACE_STORAGE.md), so its
bytes are restored from the archive into an isolated runtime folder and verified
against the archive manifest before use. Archived evidence still records the
repository's former absolute path; only the path below the project folder is used.
"""
import json
from pathlib import Path, PureWindowsPath
from uuid import uuid4
import shutil
import zipfile

from evidence.graph import EvidenceGraph
from evidence.store import EvidenceStore
from state.io import read_json,sha256,write_json
from state.project import Project

ARCHIVE="implementation/ARCHIVES/project_fixtures_20261024.zip"


def restore_archived_project(root,project_id):
    """Extract one archived proof project into runtime/test_fixtures, verifying every byte."""
    folder=root/"runtime/test_fixtures/archived"/project_id;prefix="projects/"+project_id+"/"
    with zipfile.ZipFile(root/ARCHIVE) as archive:
        rows=[row for row in json.loads(archive.read("ARCHIVE_MANIFEST.json"))["files"] if row["path"].startswith(prefix)]
        if not rows:raise ValueError("Archived proof project is missing")
        for row in rows:
            target=folder/row["path"][len(prefix):]
            if target.is_file() and sha256(target)==row["sha256"]:continue
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(row["path"]))
            if sha256(target)!=row["sha256"]:raise ValueError("Archived proof bytes do not match their manifest")
    return folder


def archived_location(folder,project_id,recorded):
    parts=PureWindowsPath(recorded).parts
    index=max(i for i,part in enumerate(parts) if part==project_id)
    return folder.joinpath(*parts[index+1:])


def prepare(root,prefix="live-native"):
    proof=read_json(root/"implementation/PHASE_REPORTS/phase_9_live_smoke.json")
    original=restore_archived_project(root,proof["project_id"]);canonical=original/"presentation/canonical.pptx"
    if not proof["passed"] or sha256(canonical)!=proof["state"]["candidate_sha256"]:raise ValueError("The verified source fixture changed")
    project=Project.create(root,prefix+"-"+uuid4().hex[:10]);store=EvidenceStore(root,project)
    graph=EvidenceGraph(read_json(original/"state/evidence_graph.json"))
    for source in graph.value["sources"].values():
        for version in [source,*source.get("previous_versions",[])]:
            old=archived_location(original,proof["project_id"],version["materialized_path"]);target=project.path/"input/sources"/source["source_id"]/version["sha256"]/old.name
            store.registry.materialize(old,target,"supporting_source");version["materialized_path"]=str(target)
    store.save(graph)
    spec=read_json(original/"work/offline_runs"/proof["run_id"]/proof["state"]["spec"])
    source=project.path/"work"/("fixture_"+uuid4().hex[:8]+".pptx");shutil.copy2(canonical,source)
    write_json(project.path/"state/live_fixture_provenance.json",{"fixture":True,"original_project_id":proof["project_id"],"original_archive":ARCHIVE,"source_pptx_sha256":sha256(source),"source_numbers":[4,1],"policy":"Independent evaluation clone; original source locations and hashes retained"})
    return project,source,spec
