"""Checkpoint render timeout/recovery verification and the actual ingestion result."""
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree
import hashlib
import json
import zipfile
from state.io import read_json,write_json,read_yaml,write_yaml,sha256

root=Path(__file__).resolve().parents[1]
tests={}
for name in ['render_timeout_tests','render_recovery_unit']:
    suite=ElementTree.parse(root/f'implementation/{name}.xml').getroot().find('testsuite')
    tests[name]={key:int(suite.get(key,0)) for key in ['tests','failures','errors','skipped']}
    assert tests[name]['tests'] and not any(tests[name][key] for key in ['failures','errors','skipped'])
batch_path=max((root/'library/references/manifests').glob('batch_*.json'),key=lambda path:path.stat().st_mtime_ns)
batch=read_json(batch_path)
source=root/'library/references/database/originals/Kick Off - FMCG Manufacturing Pre-FS.pptx'
assert sha256(source)=='702fc98f430f8789565c9f7dadbb1d95048dcd004feb6b446ab75989c397e9f0'
report={'time':datetime.now(timezone.utc).isoformat(),'status':'verified' if batch.get('passed',not batch['counts'].get('failed')) else 'code_verified_native_pending','tests':tests,'source_unchanged':True,'changes':['Automatic bounded render budget based on requested slide count','Durable stage/slide/shape progress on timeout','Recovery closes only exact hash-verified saved read-only render copies after worker exit'],'recovered_orphan':'runtime/native_render/b0fdaf7f504845608a3692ccbf90cdec/input.pptx','native_batch':batch_path.relative_to(root).as_posix(),'native_result':batch}
report_path=root/'implementation/PHASE_REPORTS/render_timeout_20261022.json'
write_json(report_path,report)
checkpoint=root/'implementation/CHECKPOINTS/render_timeout_20261022.zip'
state_path=root/'implementation/IMPLEMENTATION_STATUS.yaml'
state=read_yaml(state_path)
state['maintenance']['render_timeout']={'status':report['status'],'feature_report':report_path.relative_to(root).as_posix(),'tests':tests,'last_checkpoint':{'type':'verified_maintenance_snapshot','path':checkpoint.relative_to(root).as_posix()}}
write_yaml(state_path,state)
names=['src/presentation/rendering/native.py','src/presentation/rendering/metrics.py','src/presentation/rendering/recovery.py','scripts/powerpoint_render_worker.py','scripts/powerpoint_render_recovery.py','scripts/inspect_render_session.py','scripts/diagnose_reference_timeout.py','scripts/checkpoint_render_timeout.py','tests/unit/test_render_timeout.py','tests/unit/test_render_recovery.py','implementation/IMPLEMENTATION_STATUS.yaml','implementation/PHASE_REPORTS/render_timeout_20261022.json','implementation/render_timeout_tests.xml','implementation/render_recovery_unit.xml',batch_path.relative_to(root).as_posix()]
payloads={name:(root/name).read_bytes() for name in names}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(checkpoint,'x',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps({'status':report['status'],'native_counts':batch['counts'],'rendered_slides':batch['rendered_slides'],'checkpoint':str(checkpoint)},indent=2))
