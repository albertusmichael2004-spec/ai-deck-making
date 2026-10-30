"""Verify requested removals and checkpoint the storage routing change."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
import zipfile

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'src'))
from state.io import read_json,read_yaml,write_json,write_yaml,sha256
from ir.validation import validate
report_path=root/'implementation/PHASE_REPORTS/workspace_cleanup_20261024.json'
report=read_json(report_path)
assert report['deleted'] and report['status']=='complete'
assert not (root/'runtime/pytest').exists()
remaining=sorted(p.name for p in (root/'projects').iterdir() if p.is_dir())
assert remaining==sorted(report['kept_projects'])==['Skha','skha-ce41e6']
assert read_json(root/'projects/.active_project.json')['project_id']=='skha-ce41e6'
assert sha256(Path(report['archive']))==report['archive_sha256']
with zipfile.ZipFile(report['archive']) as archive:
    manifest=json.loads(archive.read('ARCHIVE_MANIFEST.json'))
    assert len(manifest['files'])==report['file_count'] and manifest['fixtures']==report['fixtures']
suite=ET.parse(root/'implementation/cleanup_storage_verified.xml').getroot().find('testsuite')
tests={key:int(suite.get(key,0)) for key in ['tests','errors','failures','skipped']}
assert tests['tests'] and not any(tests[key] for key in ['errors','failures','skipped']),tests
files=['src/state/paths.py','src/state/workspace.py','src/presentation/live/windows.py','tests/benchmarks/consulting_subset.py','tests/unit/test_fixture_storage.py','scripts/archive_project_fixtures.py','scripts/find_cleanup_links.py','scripts/remove_verified_test_folders.ps1','scripts/finalize_workspace_cleanup.ps1','scripts/checkpoint_workspace_cleanup.py','docs/WORKSPACE_STORAGE.md']
for name in files:
    if name.endswith('.py'):ast.parse((root/name).read_text(encoding='utf-8-sig'))
report.update(completed_at=datetime.now(timezone.utc).isoformat(),tests=tests,remaining_projects=remaining,future_fixture_root='runtime/test_projects',verification_temporary_folders_removed=True)
write_json(report_path,report)
state_path=root/'implementation/IMPLEMENTATION_STATUS.yaml';state=read_yaml(state_path)
checkpoint='implementation/CHECKPOINTS/workspace_cleanup_20261024.zip'
state.setdefault('maintenance',{})['workspace_cleanup']={'status':'verified','feature_report':report_path.relative_to(root).as_posix(),'tests':tests,'archived_fixture_count':report['fixture_count'],'pytest_removed':True,'last_checkpoint':{'type':'verified_maintenance_snapshot','path':checkpoint}}
validate(root,'implementation_state',state);write_yaml(state_path,state)
files+=['implementation/PHASE_REPORTS/workspace_cleanup_plan_20261024.json','implementation/PHASE_REPORTS/workspace_cleanup_20261024.json','implementation/cleanup_storage_verified.xml','implementation/IMPLEMENTATION_STATUS.yaml']
payloads={name:(root/name).read_bytes() for name in files}
hashes={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(root/checkpoint,'x',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(hashes,indent=2))
    archive.writestr('ARCHIVE_REFERENCE.json',json.dumps({'path':report['archive'],'sha256':report['archive_sha256'],'files':report['file_count']},indent=2))
with zipfile.ZipFile(root/checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in hashes.items())
print(json.dumps({'removed_fixtures':report['fixture_count'],'pytest_removed':True,'remaining_projects':remaining,'tests':tests,'archive':report['archive'],'checkpoint':checkpoint},indent=2))
