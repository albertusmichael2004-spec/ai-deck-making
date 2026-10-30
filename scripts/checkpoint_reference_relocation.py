"""Record verified relocation code and remaining native-render blocker."""
from pathlib import Path
import hashlib
import json
import zipfile
from xml.etree import ElementTree
from state.io import read_json, read_yaml, write_json, write_yaml

root=Path(__file__).resolve().parents[1]
report_path=root/'implementation/PHASE_REPORTS/reference_relocation.json'
report=read_json(report_path)
def totals(name):
    suite=ElementTree.parse(root/name).getroot().find('testsuite')
    return {key:int(suite.get(key,0)) for key in ['tests','failures','errors','skipped']}
report['focused_tests']=totals('implementation/reference_relocation_focused.xml')
assert report['focused_tests']=={'tests':3,'failures':0,'errors':0,'skipped':0}
report['regression_tests']=totals('implementation/reference_relocation_final.xml')
report['regression_limitations']=['Existing approval-history assertion fails after a changed source', 'Native renderer refuses an existing open presentation']
report['native_batch']='library/references/manifests/batch_975707d35d274dac9cea1bd5be3f6c4f.json'
batch=read_json(root/report['native_batch'])
report['native_result']=batch
report['status']='path_repaired_native_pending_open_presentation'
write_json(report_path,report)
checkpoint=root/'implementation/CHECKPOINTS/reference_relocation_20261020.zip'
state_path=root/'implementation/IMPLEMENTATION_STATUS.yaml'
state=read_yaml(state_path)
state['maintenance']['reference_relocation']={'status':report['status'],'feature_report':report_path.relative_to(root).as_posix(),'focused_tests':report['focused_tests'],'regression_tests':report['regression_tests'],'last_checkpoint':{'type':'verified_maintenance_snapshot','path':checkpoint.relative_to(root).as_posix()}}
write_yaml(state_path,state)
names=['src/references/migration.py','src/cli/reference_commands.py','tests/integration/test_reference_relocation.py','scripts/repair_reference_relocation.py','scripts/checkpoint_reference_relocation.py','implementation/IMPLEMENTATION_STATUS.yaml','implementation/PHASE_REPORTS/reference_relocation.json','implementation/reference_relocation_focused.xml','implementation/reference_relocation_final.xml']
payloads={name:(root/name).read_bytes() for name in names}
for path in Path(report['backup']).glob('*.json'):payloads['recovery/'+path.name]=path.read_bytes()
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(checkpoint,'x',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps({'status':report['status'],'tests':report['focused_tests'],'regression':report['regression_tests'],'checkpoint':str(checkpoint)},indent=2))
