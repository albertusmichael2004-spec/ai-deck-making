"""Record same-target regression/native proofs and a recoverable code snapshot."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

from state.io import read_json,read_yaml,write_json,write_yaml,native_path,logical_path,sha256
from ir.validation import validate
from state.project import Project

root=Path(__file__).resolve().parents[1]
suite=ET.parse(root/"implementation/target_verified_final.xml").getroot().find("testsuite")
tests={key:int(suite.get(key,0)) for key in ["tests","failures","errors","skipped"]}
assert tests["tests"] and not any(tests[key] for key in ["failures","errors","skipped"]),tests
native=read_json(root/"implementation/PHASE_REPORTS/target_update_native_20261022.json")
assert native["passed"] and len(native["cases"])==3 and native["unrelated_presentations_preserved"]
evidence=[]
fixture=Project.open(root,native["project_id"])
proof_sources=[fixture.canonical,*list((fixture.path/"history/snapshots").glob("*.pptx"))]
for case in native["cases"]:
    render=Path(case["render_report"])
    report=read_json(render)
    assert case["passed"] and report["passed"] and report["input_sha256"]==case["sha256"]
    source=next((path for path in proof_sources if sha256(path)==case["sha256"]),None)
    assert source is not None,"Retained native source bytes are required"
    evidence.append(source)
    qa=read_json(render.with_name("qa_report.json"));assert qa["passed"]
    evidence.extend([render,render.with_name("qa_report.json"),render.with_name("preview.png")])
    evidence.extend(Path(slide["render"]) for slide in report["slides"])
names=["src/state/project.py","src/state/io.py","src/state/workspace.py","src/security/files.py",
       "src/presentation/live/target_update.py","src/presentation/live/windows.py","src/presentation/backends/windows_probe.py","src/presentation/backends/ooxml.py","src/presentation/rendering/native.py","src/cli/live_commands.py","scripts/powerpoint_render_worker.py",
       "config/capability_profiles/kernel.yaml","docs/LIVE_POWERPOINT.md","docs/STYLE_REVISION.md","docs/TARGET_UPDATES.md","docs/WORKSPACE_STORAGE.md",
       "tests/integration/test_target_update.py","tests/unit/test_target_selection.py","tests/unit/test_native_render_diagnostics.py","tests/unit/test_office_preflight.py",
       "scripts/verify_target_updates.py","scripts/close_owned_target_test_decks.py","scripts/checkpoint_target_updates.py",
       "implementation/target_verified_final.xml","implementation/PHASE_REPORTS/target_update_native_20261022.json","implementation/PHASE_REPORTS/target_test_cleanup_20261022.json"]
for name in names:
    if name.endswith(".py"):ast.parse((root/name).read_text(encoding="utf-8-sig"),filename=name)
feature="implementation/PHASE_REPORTS/target_updates_20261022.json"
checkpoint="implementation/CHECKPOINTS/target_updates_20261022.zip"
report={"status":"same_target_logic_and_real_native_verified","time":datetime.now(timezone.utc).isoformat(),"tests":tests,
        "native_cases":native["cases"],"unrelated_presentations_preserved":True,"working_files_per_project":1,
        "behavior":["Borrow the running app for native QA; close only the owned read-only render copy","Keep the selected managed canonical path for commits whether target is open or closed","Retain and register user drafts before revision, then detect concurrent changes before releasing the saved target","Atomically commit the validated candidate and reopen the same target at its previous slide","Reopen the old target on replacement failure; retained refresh intent is recoverable","Ignore inaccessible preview metadata instead of invalidating the whole application","Default live CLI attach to project canonical, open-if-missing and save-existing; explicit manual mode remains available"],
        "scope":"Application lifecycle fixes; actual user presentations were not revised. Native tests used isolated synthetic qa-smoke projects and actual PowerPoint rendering/deterministic QA. Existing Critic/evidence/protected/recovery gates are unchanged.",
        "native_environment":{"preexisting_presentation_count":native["preexisting_count"],"empty_app_covered_by_unit":True,"real_native_covered_running_app_with_other_presentations":True},
        "documentation":"docs/TARGET_UPDATES.md","sources":["https://learn.microsoft.com/en-us/office/vba/api/powerpoint.presentations.open","https://learn.microsoft.com/zh-cn/answers/questions/5397135/ppt-slideshowwindow-%28unknown-member%29-invalid-reque"]}
write_json(root/feature,report)
markdown="implementation/PHASE_REPORTS/target_updates_20261022.md"
(root/markdown).write_text(f'''# Pembaruan target PowerPoint yang sama

Perubahan telah diverifikasi dengan {tests['tests']} tes regresi dan tiga skenario PowerPoint sungguhan: target terbuka, target terbuka dengan draft belum disimpan, dan target tertutup ketika PowerPoint tetap berjalan. Setiap revisi memperbarui canonical pada path yang sama; draft pengguna dan presentasi lain tetap terjaga. Target terbuka kembali di slide sebelumnya. Skenario app kosong juga dicakup unit test worker dengan jumlah presentasi nol.

Studio memakai salinan read-only internal untuk QA dan menutup hanya salinan itu. File yang dikunci Office dibaca dengan sharing flags Windows yang kompatibel; lock tidak dipaksa dibuka. Sumber dari target terbuka dicadangkan dan disimpan melalui otoritas live sebelum revisi file. Sesudah gate validasi yang sudah ada lolos, canonical diganti atomik dan jendela target di-refresh. Jika ada edit baru selama QA, penggantian ditolak dan edit pengguna dipertahankan. Gagal replace membuka kembali file lama; project recover memulihkan refresh yang terputus.

Tidak ada SaveAs atau file output bernomor sebagai fallback. Impor asli tetap immutable; salinan kerja/QA/recovery di folder internal bukan target baru. Perbaikan lifecycle ini diterapkan ke project commit yang dipakai revise/run, dan live attach default ke canonical proyek dengan save_existing. Parameter manual/require-open tetap tersedia.

Uji native memakai fixture sintetis {native['project_id']}; bukan revisi presentasi bisnis pengguna. Render, deterministic QA, evidence, Critic, protected-object dan recovery gate tetap dipertahankan. Detail kontrak dan sumber dokumentasi Microsoft tersedia di docs/TARGET_UPDATES.md.
''',encoding="utf-8")
state_path=root/"implementation/IMPLEMENTATION_STATUS.yaml";state=read_yaml(state_path)
state.setdefault("maintenance",{})["target_updates"]={"status":report["status"],"feature_report":feature,"tests":tests,"native_cases":3,"last_checkpoint":{"type":"verified_maintenance_snapshot","path":checkpoint}}
validate(root,"implementation_state",state);write_yaml(state_path,state)
names.extend(["implementation/IMPLEMENTATION_STATUS.yaml",feature,markdown])
names.extend(logical_path(native_path(path)).relative_to(root).as_posix() for path in evidence)
payloads={name:(root/name).read_bytes() for name in names}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(root/checkpoint,"x",zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr("CHECKPOINT_MANIFEST.json",json.dumps(manifest,indent=2))
with zipfile.ZipFile(root/checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps({"tests":tests,"native_cases":3,"checkpoint":checkpoint,"report":markdown},indent=2))
