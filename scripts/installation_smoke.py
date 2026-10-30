"""Install the source checkout into an isolated venv using verified local dependencies."""
import importlib.metadata
import json
import os
import subprocess
import sys
import venv
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from state.io import write_json


def main():
    folder=ROOT/"runtime/installation_smoke"/uuid4().hex;folder.mkdir(parents=True)
    venv.EnvBuilder(with_pip=True,system_site_packages=True).create(folder/"venv")
    python=folder/"venv/Scripts/python.exe" if os.name=="nt" else folder/"venv/bin/python"
    site=folder/"venv/Lib/site-packages" if os.name=="nt" else folder/"venv/lib"/("python"+str(sys.version_info.major)+"."+str(sys.version_info.minor))/"site-packages"
    (site/"studio_workspace_dependencies.pth").write_text(str(ROOT/"runtime/python_packages")+"\n",encoding="utf-8")
    commands=[[str(python),"-m","pip","install","--no-cache-dir","--no-deps","--no-build-isolation","-e",str(ROOT)],[str(python),"-m","pip","check"],[str(python),"-m","cli.main","--root",str(ROOT),"status"],[str(python),"-m","cli.main","live","--help"],[str(python),"-m","cli.main","compile","--spec",str(ROOT/"tests/fixtures/basic_spec.json"),"--output",str(folder/"installed_fixture.pptx")],[str(python),"-m","cli.main","inspect",str(folder/"installed_fixture.pptx")]]
    env=os.environ.copy();env.pop("PYTHONPATH",None);results=[]
    for index,command in enumerate(commands):
        value=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",timeout=180,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        (folder/f"step_{index}.txt").write_text(value.stdout+value.stderr,encoding="utf-8")
        results.append({"command":command[1:4],"passed":value.returncode==0,"returncode":value.returncode})
        if value.returncode:break
    report={"passed":len(results)==len(commands) and all(row["passed"] for row in results),"method":"Isolated editable venv with system_site_packages and the verified local standards-validator runtime; no dependency downloads or global modifications","version":"1.0.0","python":sys.version,"environment":str(folder),"steps":results,"dependencies":{name:importlib.metadata.version(name) for name in ["PyYAML","jsonschema","python-pptx","lxml","openpyxl","PyMuPDF","python-docx","Pillow","pywin32"]}}
    write_json(ROOT/"implementation/PHASE_REPORTS/phase_11_installation.json",report)
    print({"passed":report["passed"],"steps":results},flush=True)
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
