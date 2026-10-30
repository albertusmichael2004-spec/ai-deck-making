"""Verify the workspace venv and checkpoint the locator fallback configuration."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
settings=json.loads((ROOT/'.vscode/settings.json').read_text())
assert settings['python.useEnvironmentsExtension'] is False
interpreter=Path(settings['python.defaultInterpreterPath'])
assert interpreter.is_file()
environment=dict(os.environ,PYTHONPATH='',PYTHONUTF8='1')
probe=subprocess.run([str(interpreter),'-c',"import sys,json,yaml,jsonschema,pptx,lxml,openpyxl,fitz,docx,PIL,win32com; print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'version':sys.version}))"],cwd=ROOT,env=environment,capture_output=True,text=True,timeout=60)
assert probe.returncode==0,probe.stderr
runtime=json.loads(next(line for line in reversed(probe.stdout.splitlines()) if line.startswith('{')))
assert Path(runtime['prefix'])==ROOT/'.venv'
assert runtime['prefix']!=runtime['base_prefix']
check=subprocess.run([str(interpreter),'-m','pip','check'],cwd=ROOT,env=environment,capture_output=True,text=True,timeout=60)
assert check.returncode==0,check.stdout+check.stderr
sys.path.insert(0,str(ROOT/'runtime/python_packages'))
import yaml
report={'status':'configuration_and_venv_verified_reload_pending','time':datetime.now(timezone.utc).isoformat(),'runtime':runtime,'dependency_check':check.stdout.strip(),'cause':'Environment Locator configure timeout occurred before resolution; the same venv path later resolved successfully in the log.','change':'Use the Python extension legacy environment manager for this workspace (python.useEnvironmentsExtension=false).','evidence':'Code/logs/20261022T133635/window1/exthost/ms-python.vscode-python-envs/Python Environments.log','limitation':'Actual editor activation after reload has not been verified.'}
report_path=ROOT/'implementation/PHASE_REPORTS/interpreter_resolution_20261022.json'
report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
state_path=ROOT/'implementation/IMPLEMENTATION_STATUS.yaml'
state=yaml.safe_load(state_path.read_text(encoding='utf-8'))
checkpoint=ROOT/'implementation/CHECKPOINTS/interpreter_resolution_20261022.zip'
state['maintenance']['interpreter_resolution']={'status':report['status'],'feature_report':report_path.relative_to(ROOT).as_posix(),'last_checkpoint':{'type':'verified_maintenance_snapshot','path':checkpoint.relative_to(ROOT).as_posix()}}
state_path.write_text(yaml.safe_dump(state,sort_keys=False),encoding='utf-8')
names=['.vscode/settings.json','.vscode/launch.json','.vscode/tasks.json','scripts/verify_interpreter_resolution.py','implementation/PHASE_REPORTS/interpreter_resolution_20261022.json','implementation/IMPLEMENTATION_STATUS.yaml']
payloads={name:(ROOT/name).read_bytes() for name in names}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(checkpoint,'x',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps(report,indent=2))
