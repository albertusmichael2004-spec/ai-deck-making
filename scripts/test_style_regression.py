"""File/logic tests for styling fixes; native tests require exclusive Office."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

root=Path(__file__).resolve().parents[1]
files=sorted(p.relative_to(root).as_posix() for folder in ["unit","regression","integration"] for p in (root/"tests"/folder).glob("test_*.py") if "native" not in p.name)
command=[sys.executable,"-m","pytest",*files,"-q","--tb=short","--basetemp="+str(root/"runtime/pytest"/uuid4().hex),"--junitxml=implementation/style_logic_final.xml"]
for case in ["tests/integration/test_others_workspace.py::test_native_quick_import_revision_and_separate_tasks_keep_original_unchanged","tests/integration/test_project_workspace.py::test_production_target_import_requires_real_native_qa","tests/integration/test_reference_scopes.py::test_real_native_unified_database_and_scoped_project"]:
    command.extend(["--deselect",case])
raise SystemExit(subprocess.run(command,cwd=root,env=dict(os.environ,PYTHONUTF8="1")).returncode)
