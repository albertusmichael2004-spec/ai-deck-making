"""Verify terminal startup, launcher regression, and record a maintenance checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'runtime/python_packages')]
import run
import yaml

environment = dict(os.environ)
environment['PYTHONPATH'] = os.pathsep.join(sys.path[:3])
test_temp = ROOT / 'runtime/terminal_tests' / uuid4().hex
test_temp.parent.mkdir(parents=True, exist_ok=True)
tests = subprocess.run([sys.executable, '-m', 'pytest', 'tests/unit/test_run_launcher.py', '-q', f'--basetemp={test_temp}', '--junitxml=implementation/terminal_startup_regression.xml'], cwd=ROOT, env=environment)
if tests.returncode:
    raise SystemExit(tests.returncode)
start = time.perf_counter()
interpreter = run._find_project_interpreter()
probe_seconds = time.perf_counter() - start
# Send a command over stdin after the startup script has run, without opening a GUI.
startup = str(ROOT / 'scripts/terminal.ps1').replace("'", "''")
shell = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f"& '{startup}'; (Get-Location).Path; $env:VIRTUAL_ENV; (Get-Command python).Source"], cwd=ROOT, capture_output=True, text=True, timeout=30)
assert shell.returncode == 0, shell.stderr
assert not shell.stderr.strip(), shell.stderr
assert str(ROOT).lower() in shell.stdout.lower(), shell.stdout
assert str(ROOT / '.venv').lower() in shell.stdout.lower(), shell.stdout
assert interpreter == ROOT / '.venv/Scripts/python.exe', interpreter
start = time.perf_counter()
menu = subprocess.run([str(interpreter), str(ROOT / 'run.py'), '--in-terminal'], input='q\n', capture_output=True, text=True, cwd=ROOT, timeout=30)
assert menu.returncode == 0, menu.stderr
assert menu.stdout.strip(), 'Menu did not render'
report = {'status': 'verified', 'time': datetime.now(timezone.utc).isoformat(), 'interpreter': str(interpreter), 'probe_seconds': probe_seconds, 'menu_seconds': time.perf_counter()-start, 'terminal_path': shell.stdout.strip(), 'tests': 'implementation/terminal_startup_regression.xml', 'limitation': 'Existing editor terminals must be recreated; actual Run button was not controlled.'}
report_path = ROOT / 'implementation/PHASE_REPORTS/venv_startup.json'
report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
state_path = ROOT / 'implementation/IMPLEMENTATION_STATUS.yaml'
state = yaml.safe_load(state_path.read_text(encoding='utf-8'))
checkpoint = ROOT / 'implementation/CHECKPOINTS/venv_startup_20261020.zip'
state['maintenance']['venv_startup'] = {'status': 'complete', 'feature_report': report_path.relative_to(ROOT).as_posix(), 'last_checkpoint': {'type': 'verified_maintenance_snapshot', 'path': checkpoint.relative_to(ROOT).as_posix()}}
state_path.write_text(yaml.safe_dump(state, sort_keys=False), encoding='utf-8')
files = ['run.py', 'pyproject.toml', '.venv/pyvenv.cfg', '.venv/Scripts/Activate.ps1', '.vscode/settings.json', '.vscode/launch.json', 'scripts/terminal.ps1', 'scripts/studio.ps1', 'scripts/verify_terminal_startup.py', 'tests/unit/test_run_launcher.py', 'implementation/IMPLEMENTATION_STATUS.yaml', 'implementation/PHASE_REPORTS/venv_startup.json', 'implementation/terminal_startup_regression.xml']
payloads = {name: (ROOT / name).read_bytes() for name in files}
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
with zipfile.ZipFile(checkpoint, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name, data in payloads.items():
        archive.writestr(name, data)
    archive.writestr('CHECKPOINT_MANIFEST.json', json.dumps(manifest, indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in manifest.items())
print(json.dumps(report, indent=2))
