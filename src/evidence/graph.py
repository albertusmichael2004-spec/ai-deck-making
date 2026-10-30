from copy import deepcopy
from datetime import datetime, timezone

from evidence.calculation import calculate,validate_units,CALCULATION_PRECISION
from evidence.dependencies import DependencyGraph
from state.errors import StudioError, ErrorCode


class EvidenceGraph:
    TYPES = {"raw_fact", "calculated_fact", "interpretation", "hypothesis", "recommendation"}

    def __init__(self, value=None):
        self.value = value or {"schema_version":"1.0","sources":{},"nodes":{},"dependencies":{},"bindings":{}}
        self.dependencies = DependencyGraph(self.value["dependencies"])

    def register(self, node):
        node = deepcopy(node)
        identifier = node["evidence_id"]
        if node["type"] not in self.TYPES or not 0 <= node.get("confidence", 1) <= 1:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid evidence type or confidence")
        if identifier in self.value["nodes"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Evidence identity already exists")
        inputs = node.get("supported_by", [])
        if any(key not in self.value["nodes"] for key in inputs):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unresolved supporting evidence")
        if node["type"] in {"calculated_fact", "interpretation", "recommendation"} and not inputs:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Material conclusions require supporting evidence")
        if node["type"] in {"interpretation", "recommendation"} and not any(item["type"] in {"raw_fact", "calculated_fact"} for key in inputs for item in self.trace(key)):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Hypotheses alone cannot ground a material conclusion")
        if node["type"] == "raw_fact" and (not node.get("source_id") or node["source_id"] not in self.value["sources"] or not node.get("locator")):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Raw fact requires registered source and exact locator")
        node.setdefault("status", "current")
        if any(self.resolve(key)["status"] != "current" for key in inputs):node["status"]="stale"
        node.setdefault("confidence", 1)
        node.setdefault("assumptions", [])
        self.dependencies.register(identifier, inputs)
        self.value["nodes"][identifier] = node
        return identifier

    def calculate(self, identifier, formula, inputs, unit):
        nodes = {variable:self.resolve(evidence) for variable,evidence in inputs.items()}
        if any(node["status"] != "current" for node in nodes.values()):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Calculation depends on unverified or stale evidence")
        validate_units(nodes,unit)
        result = calculate(formula,{key:node["value"] for key,node in nodes.items()},{key:node["unit"] for key,node in nodes.items()},unit)
        snapshot={key:{"evidence_id":node["evidence_id"],"value":node["value"],"unit":node["unit"],"source_sha256":node.get("source_sha256")} for key,node in nodes.items()}
        return self.register({"evidence_id":identifier,"type":"calculated_fact","formula":formula,"variables":inputs,"supported_by":list(inputs.values()),"value":result,"unit":unit,"input_snapshot":snapshot,"calculation_engine":{"method":"decimal_arithmetic","precision":CALCULATION_PRECISION},"confidence":min(n["confidence"] for n in nodes.values()),"assumptions":[]})

    def resolve(self, identifier):
        if identifier not in self.value["nodes"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Evidence not found", evidence_id=identifier)
        return self.value["nodes"][identifier]

    def trace(self, identifier):
        seen, result = set(), []
        def visit(key):
            if key in seen: return
            seen.add(key);node=self.resolve(key);result.append(deepcopy(node))
            for parent in node.get("supported_by", []): visit(parent)
        visit(identifier)
        return result

    def bind(self, binding_id, evidence_ids, slide_id, exhibit_id):
        for key in evidence_ids:
            if self.resolve(key)["status"] != "current":
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Cannot bind stale or unverified evidence")
        if binding_id in self.value["bindings"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Binding already exists")
        self.dependencies.register(binding_id,evidence_ids)
        self.dependencies.register(exhibit_id,[binding_id])
        self.dependencies.register(slide_id,[*self.dependencies.dependencies.get(slide_id,[]),exhibit_id])
        self.value["bindings"][binding_id]={"binding_id":binding_id,"evidence_ids":evidence_ids,"slide_id":slide_id,"exhibit_id":exhibit_id}

    def gaps(self, questions):
        result=[]
        for question in questions:
            supports = question.get("evidence_ids", [])
            accepted=question.get("accepted_types",["raw_fact","calculated_fact","interpretation"])
            missing=[key for key in supports if key not in self.value["nodes"] or self.value["nodes"][key]["status"] != "current" or self.value["nodes"][key]["type"] not in accepted or self.value["nodes"][key]["confidence"] < question.get("minimum_confidence",.8)]
            freshness_problem=False
            if question.get("max_age_days") is not None:
                now=datetime.now(timezone.utc)
                for key in supports:
                    if key not in self.value["nodes"]:continue
                    for evidence in self.trace(key):
                        if evidence["type"]!="raw_fact":continue
                        date=self.value["sources"][evidence["source_id"]].get("source_date")
                        try:
                            asof=datetime.fromisoformat(date)
                            if asof.tzinfo is None:asof=asof.replace(tzinfo=timezone.utc)
                            if (now-asof).days>question["max_age_days"]:freshness_problem=True
                        except (TypeError,ValueError):freshness_problem=True
            if not supports or missing or freshness_problem:
                result.append({"question_id":question["question_id"],"question":question["question"],"material":question.get("material",True),"reason":"freshness_unknown_or_stale" if freshness_problem else "missing_or_unverified_evidence","unresolved_ids":missing})
        return result
