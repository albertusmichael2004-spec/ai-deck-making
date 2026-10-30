"""Validate workspace configuration and smoke-test the direct VS Code task command."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/python_packages'))
import yaml

settings = json.loads((ROOT / '.vscode/settings.json').read_text())
assert Path(settings['python.defaultInterpreterPath']).is_file()
for name in ['launch', 'tasks']:
    json.loads((ROOT / f'.vscode/{name}.json').read_text())
task = json.loads((ROOT / '.vscode/tasks.json').read_text())['tasks'][0]
command = [task['command'], *task['args']]
command = [value.replace('${workspaceFolder}', str(ROOT)) for value in command]
start = time.perf_counter()
result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONUTF8='1'), input='q\n', capture_output=True, text=True, timeout=60)
assert result.returncode == 0, result.stderr
assert result.stdout.strip()
report = {
    'status': 'verified_config_and_direct_command',
    'time': datetime.now(timezone.utc).isoformat(),
    'observed_log': '20261020T150400/window1/exthost',
    'evidence': ['workspaceContains searches timed out after about 43 seconds', 'PET configure timed out and retried with 60000ms timeout', 'defaultInterpreterPath with workspaceFolder variable was unresolvable; Python 3.14 was auto-selected'],
    'changes': ['Absolute venv interpreter path', 'Only .venv in environment workspace search paths', 'Exclude generated/data trees from editor search, file watching and Pylance analysis', 'Default build task runs venv Python directly without a Python extension command'],
    'direct_task_command_seconds': time.perf_counter()-start,
    'limitation': 'Editor reload and actual extension activation latency have not been verified in the UI.'
}
report_path = ROOT / 'implementation/PHASE_REPORTS/editor_startup.json'
report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
state_path = ROOT / 'implementation/IMPLEMENTATION_STATUS.yaml'
state = yaml.safe_load(state_path.read_text(encoding='utf-8'))
checkpoint = ROOT / 'implementation/CHECKPOINTS/editor_startup_20261020.zip'
state['maintenance']['editor_startup'] = {'status': 'configuration_verified_reload_pending', 'feature_report': report_path.relative_to(ROOT).as_posix(), 'last_checkpoint': {'type': 'verified_maintenance_snapshot', 'path': checkpoint.relative_to(ROOT).as_posix()}}
state_path.write_text(yaml.safe_dump(state, sort_keys=False), encoding='utf-8')
files = ['.vscode/settings.json', '.vscode/launch.json', '.vscode/tasks.json', 'scripts/verify_editor_startup.py', 'implementation/IMPLEMENTATION_STATUS.yaml', 'implementation/PHASE_REPORTS/editor_startup.json']
payloads = {name: (ROOT/name).read_bytes() for name in files}
manifest = {name: hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(checkpoint, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():
        archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps(report,indent=2))
