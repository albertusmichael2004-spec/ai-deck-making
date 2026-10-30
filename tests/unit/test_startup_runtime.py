"""Fresh-process checks keep optional engines off the idle menu path."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]


def test_menu_does_not_load_optional_engines():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/benchmark_startup.py'),'--worker','cli'],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    sample=json.loads(result.stdout.strip().splitlines()[-1])
    assert sample['heavy_imports']==[]


def test_both_root_launchers_work_from_an_unrelated_directory(tmp_path):
    for entry in ['run.py','main.py']:
        result=subprocess.run([sys.executable,str(ROOT/entry),'--in-terminal'],cwd=tmp_path,input='q\n',capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stderr
        assert 'pilih aktivitas' in result.stdout


def test_cli_file_can_run_from_an_unrelated_directory(tmp_path):
    environment=dict(os.environ,PYTHONPATH='')
    result=subprocess.run([sys.executable,str(ROOT/'src/cli/main.py'),'capabilities'],cwd=tmp_path,env=environment,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert isinstance(json.loads(result.stdout),dict)


def test_cli_explicit_invalid_root_is_not_silently_replaced(tmp_path):
    invalid=Path(ROOT.anchor)/('studio_absent_'+uuid4().hex)
    result=subprocess.run([sys.executable,str(ROOT/'src/cli/main.py'),'--root',str(invalid),'capabilities'],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert result.returncode!=0
    assert json.loads(result.stdout)['code']=='DATA_VALIDATION_ERROR'
