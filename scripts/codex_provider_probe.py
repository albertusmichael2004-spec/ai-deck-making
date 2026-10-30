"""Probe schema output and live search without filesystem/app execution tools."""
import json
import os
import subprocess
import tomllib
from pathlib import Path
from uuid import uuid4


root=Path(__file__).resolve().parents[1]
job=root/"runtime/provider_probe"/uuid4().hex
job.mkdir(parents=True)
schema={"type":"object","additionalProperties":False,"required":["available","sources"],"properties":{"available":{"type":"boolean"},"sources":{"type":"array","items":{"type":"object","additionalProperties":False,"required":["url","title"],"properties":{"url":{"type":"string"},"title":{"type":"string"}}}}}}
(job/"response_schema.json").write_text(json.dumps(schema),encoding="utf-8")
selected_model=None
config=Path(os.environ.get("CODEX_HOME",str(Path.home()/".codex")))/"config.toml"
if config.exists():
    parsed=tomllib.loads(config.read_text(encoding="utf-8"))
    selected_model=parsed.get("model")
    if parsed.get("model_provider","openai")!="openai":
        raise SystemExit("Probe requires an explicitly configured adapter for the custom provider; no credentials were copied")
command=["codex","--no-daemon","--search","-a","never","-s","read-only"]
for feature in ["shell_tool","unified_exec","apps","plugins","hooks","computer_use","browser_use","view_image","image_generation"]:command.extend(["--disable",feature])
command.extend(["exec","--ephemeral","--ignore-user-config","--skip-git-repo-check","--json","--output-schema",str(job/"response_schema.json"),"-C",str(job),"-"])
if selected_model:command.extend(["-m",selected_model])
prompt="Capability smoke test for a read-only web search adapter. Use only native web search. Find the official NASA Mars overview page and return its URL and title in the requested JSON schema. Do not use shell, filesystem, apps, MCP or other tools. Do not inspect local data. If live web search is unavailable, return available=false and sources=[]."
try:
    result=subprocess.run(command,input=prompt,capture_output=True,text=True,encoding="utf-8",timeout=120,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    events=[]
    for line in result.stdout.splitlines():
        try:events.append(json.loads(line))
        except json.JSONDecodeError:pass
    tool_types=[event.get("item",{}).get("type") for event in events if event.get("type")=="item.completed"]
    errors=[event for event in events if event.get("type") in {"error","turn.failed"} or event.get("item",{}).get("type")=="error"]
    final=[event["item"]["text"] for event in events if event.get("type")=="item.completed" and event.get("item",{}).get("type")=="agent_message"]
    response=json.loads(final[-1]) if final else None
    unsafe=any(kind in {"command_execution","mcp_tool_call"} for kind in tool_types)
    report={"schema_version":"1.0","returncode":result.returncode,"configured_model":selected_model,"passed":result.returncode==0 and bool(response and response.get("available")) and not unsafe,"tool_types":tool_types,"response":response,"errors":errors,"stderr_tail":result.stderr[-2000:]}
except subprocess.TimeoutExpired:
    report={"schema_version":"1.0","passed":False,"reason":"provider_timeout","timeout_seconds":120,"configured_model":selected_model}
target=root/"implementation/PHASE_REPORTS/phase_4_provider_probe.json"
target.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
raise SystemExit(0 if report["passed"] else 1)
