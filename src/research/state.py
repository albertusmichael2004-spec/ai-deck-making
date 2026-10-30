import json
from datetime import datetime,timezone

from state.io import read_json,write_json,write_yaml
from security.content import redact
from ir.validation import validate
import os


class ResearchState:
    def __init__(self,project):
        self.repository=project.repository
        self.path=project.policy.check(project.path/"state/research",write=True)
        self.path.mkdir(parents=True,exist_ok=True)
        sources=read_json(self.path/"source_registry.json") if (self.path/"source_registry.json").exists() else {"schema_version":"1.0","sources":{}}
        conflicts=read_json(self.path/"conflict_registry.json") if (self.path/"conflict_registry.json").exists() else {"schema_version":"1.0","conflicts":{}}
        validate(self.repository,"source_registry",sources);validate(self.repository,"conflict_registry",conflicts)
        self.sources=sources["sources"];self.conflicts=conflicts["conflicts"]

    def start(self,plan):
        validate(self.repository,"research_plan",plan)
        write_yaml(self.path/"research_plan.yaml",plan)
        self.event("research_started",research_id=plan["research_id"],mode=plan["mode"],budgets=plan["budgets"])

    def event(self,event,**values):
        record=redact({"schema_version":"1.0","time":datetime.now(timezone.utc).isoformat(),"event":event,**values})
        # Credential redaction must not erase trusted numeric metering fields.
        if event=="provider_usage" and type(values.get("tokens"))==int:record["tokens"]=values["tokens"]
        if event=="research_stopped" and isinstance(values.get("usage"),dict):
            if type(values["usage"].get("tokens"))==int:record["usage"]["tokens"]=values["usage"]["tokens"]
        if event=="research_started" and isinstance(values.get("budgets"),dict):
            if type(values["budgets"].get("max_tokens"))==int:record["budgets"]["max_tokens"]=values["budgets"]["max_tokens"]
        validate(self.repository,"research_ledger",record)
        with (self.path/"research_ledger.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(record,allow_nan=False)+"\n");stream.flush();os.fsync(stream.fileno())

    def persist(self):
        sources={"schema_version":"1.0","sources":self.sources};conflicts={"schema_version":"1.0","conflicts":self.conflicts}
        validate(self.repository,"source_registry",sources);validate(self.repository,"conflict_registry",conflicts)
        write_json(self.path/"source_registry.json",sources)
        write_json(self.path/"conflict_registry.json",conflicts)
