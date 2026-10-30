"""Run file/logic regression without borrowing a user's open PowerPoint session."""
from pathlib import Path
import json
import os
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
files=sorted(path for folder in ['unit','regression','integration'] for path in (ROOT/'tests'/folder).glob('test_*.py'))
native_files=[path for path in files if 'native' in path.name]
selected=[path.relative_to(ROOT).as_posix() for path in files if path not in native_files]
native_cases=['tests/integration/test_others_workspace.py::test_native_quick_import_revision_and_separate_tasks_keep_original_unchanged','tests/integration/test_project_workspace.py::test_production_target_import_requires_real_native_qa','tests/integration/test_reference_scopes.py::test_real_native_unified_database_and_scoped_project']
temporary=ROOT/'runtime/pytest'/uuid4().hex
temporary.parent.mkdir(parents=True,exist_ok=True)
command=[sys.executable,'-m','pytest',*selected,'-q','--tb=short',f'--basetemp={temporary}','--junitxml=implementation/startup_logic_final.xml']
for case in native_cases:command.extend(['--deselect',case])
environment=dict(os.environ,PYTHONUTF8='1')
selection={'files':selected,'native_files_not_run':[path.relative_to(ROOT).as_posix() for path in native_files],'native_cases_not_run':native_cases,'reason':'User has an open editable PowerPoint presentation; native automation tests require exclusive ownership.'}
(ROOT/'implementation/PHASE_REPORTS/startup_test_scope.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
raise SystemExit(subprocess.run(command,cwd=ROOT,env=environment).returncode)
