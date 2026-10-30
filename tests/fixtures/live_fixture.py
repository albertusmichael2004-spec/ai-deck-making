"""Clone the proven synthetic Phase 9 artifact; preserve immutable source provenance."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import shutil

from evidence.store import EvidenceStore
from state.io import read_json,sha256,write_json
from state.project import Project


def prepare(root,prefix="live-native"):
    proof=read_json(root/"implementation/PHASE_REPORTS/phase_9_live_smoke.json")
    original=Project.open(root,proof["project_id"])
    if not proof["passed"] or sha256(original.canonical)!=proof["state"]["candidate_sha256"]:raise ValueError("The verified source fixture changed")
    project=Project.create(root,prefix+"-"+uuid4().hex[:10]);store=EvidenceStore(root,project)
    graph=EvidenceStore(root,original).load()
    for source in graph.value["sources"].values():
        for version in [source,*source.get("previous_versions",[])]:
            old=Path(version["materialized_path"]);target=project.path/"input/sources"/source["source_id"]/version["sha256"]/old.name
            store.registry.materialize(old,target,"supporting_source");version["materialized_path"]=str(target)
    store.save(graph)
    spec=read_json(original.path/"work/offline_runs"/proof["run_id"]/proof["state"]["spec"])
    source=project.path/"work"/("fixture_"+uuid4().hex[:8]+".pptx");shutil.copy2(original.canonical,source)
    write_json(project.path/"state/live_fixture_provenance.json",{"fixture":True,"original_project_id":original.path.name,"source_pptx_sha256":sha256(source),"source_numbers":[4,1],"policy":"Independent evaluation clone; original source locations and hashes retained"})
    return project,source,spec
