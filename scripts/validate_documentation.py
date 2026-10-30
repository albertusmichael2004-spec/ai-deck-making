"""Validate maintained documentation links, schema syntax and installed CLI contracts."""
import ast
import re
import sys
import json
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from state.io import write_json,read_json,sha256


def main():
    failures=[];links=0;python_files=0;schemas=0
    for file in [ROOT/"README.md",*(ROOT/"docs").rglob("*.md")]:
        if file.name=="AI_Presentation_Studio_Architecture_v6_6.md":continue
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",file.read_text(encoding="utf-8")):
            if re.match(r"[a-z]+://|#",target):continue
            target=unquote(target.split("#")[0]).strip("<>")
            links+=1
            if not (file.parent/target).exists():failures.append({"file":str(file.relative_to(ROOT)),"broken_link":target})
    for directory in ["src","scripts","tests"]:
        for file in (ROOT/directory).rglob("*.py"):
            if "__pycache__" in file.parts:continue
            python_files+=1
            try:ast.parse(file.read_text(encoding="utf-8-sig"),filename=str(file))
            except SyntaxError as exc:failures.append({"file":str(file.relative_to(ROOT)),"syntax":str(exc)})
    for file in (ROOT/"schemas").rglob("*.json"):
        schemas+=1
        try:json.loads(file.read_text(encoding="utf-8"))
        except ValueError as exc:failures.append({"file":str(file.relative_to(ROOT)),"schema":str(exc)})
    installation=read_json(ROOT/"implementation/PHASE_REPORTS/phase_11_installation.json")
    if not installation["passed"]:failures.append({"installation":"failed"})
    report={"passed":not failures,"relative_links_checked":links,"python_files_checked":python_files,"schema_files_checked":schemas,"failures":failures,"architecture_sha256":sha256(ROOT/"docs/AI_Presentation_Studio_Architecture_v6_6.md"),"command_contracts":"Actual installed CLI help, status, compile and inspect passed installation smoke; native CLI inspect/selection verified separately"}
    write_json(ROOT/"implementation/PHASE_REPORTS/phase_11_documentation.json",report)
    print(report)
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
