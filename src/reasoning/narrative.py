import re

from evidence.verification import EvidenceVerifier
from reasoning.mece import check_mece
from state.errors import StudioError


def narrative_qa(story,graph,policy,coverage_keys):
    findings=[{"code":code,"severity":"blocker"} for code in check_mece(story["issues"],coverage_keys)]
    verifier=EvidenceVerifier(policy)
    issues={row["issue_id"]:row for row in story["issues"]}
    arguments={row["argument_id"]:row for row in story["arguments"]}
    recommendations={row["recommendation_id"]:row for row in story["recommendations"]}
    def flag(code,identifier=None,severity="blocker"):findings.append({"code":code,"severity":severity,"id":identifier})
    for kind,rows,key in [("argument",story["arguments"],"argument_id"),("recommendation",story["recommendations"],"recommendation_id"),("hypothesis",story["hypotheses"],"hypothesis_id")]:
        if len({row[key] for row in rows})!=len(rows):flag("duplicate_"+kind+"_identity")
    titles=set()
    for argument in story["arguments"]:
        identifier=argument["argument_id"]
        if argument["issue_id"] not in issues:flag("unresolved_issue",identifier)
        normalized=" ".join(argument["action_title"].lower().split())
        if normalized in titles:flag("repeated_slide_message",identifier)
        titles.add(normalized)
        if len(normalized.split())<4 or normalized in {"market overview","financial analysis","recommendations","executive summary"}:flag("topic_title_without_assertion",identifier,"major")
        for evidence_id in argument["evidence_ids"]:
            try:
                node=graph.resolve(evidence_id)
                lineage=graph.trace(evidence_id)
                if node["status"]!="current" or not any(item["type"] in {"raw_fact","calculated_fact"} for item in lineage):flag("unsupported_material_claim",identifier)
                for item in lineage:
                    if item["type"] in {"raw_fact","calculated_fact"}:verifier.value(graph,item["evidence_id"])
            except StudioError:flag("invalid_claim_lineage",identifier)
        numbers=set()
        for assertion in argument["numeric_assertions"]:
            try:
                node=graph.resolve(assertion["evidence_id"])
                supported={item["evidence_id"] for key in argument["evidence_ids"] for item in graph.trace(key)}
                if assertion["evidence_id"] not in supported or assertion["unit"]!=node.get("unit",{}).get("label") or not verifier.displayed(graph,assertion["evidence_id"],assertion["displayed"]):flag("numeric_contradiction",identifier)
                numbers.add(assertion["displayed"])
            except StudioError:flag("numeric_contradiction",identifier)
        for evidence_id in argument["evidence_ids"]:
            try:
                for node in graph.trace(evidence_id):
                    numbers.update(re.findall(r"\d+(?:[.,]\d+)*",str(node.get("freshness",{}).get("data_period",""))))
            except StudioError:pass
        claimed={literal.replace("−","-") for literal in re.findall(r"(?<![0-9])[-−+]?\d+(?:[.,]\d+)*",argument["claim"]+" "+argument["action_title"]+" "+argument["implication"]+" "+argument["transition"])}
        if not claimed<=numbers:flag("unregistered_numerical_claim",identifier)
    parents={row["parent_id"] for row in story["issues"]}
    for issue in story["issues"]:
        if issue["critical"] and issue["issue_id"] not in parents and not any(row["issue_id"]==issue["issue_id"] for row in story["arguments"]):flag("critical_issue_without_argument",issue["issue_id"])
    for recommendation in story["recommendations"]:
        for key in recommendation["argument_ids"]:
            if key not in arguments:flag("recommendation_without_support",recommendation["recommendation_id"])
        for criterion in recommendation["criteria"]:
            if not set(criterion["argument_ids"])<=set(recommendation["argument_ids"]):flag("criterion_without_support",recommendation["recommendation_id"])
    core=story["core_answer"];selected=recommendations.get(core["recommendation_id"])
    if selected is None or core["text"]!=selected["text"] or set(core["argument_ids"])!=set((selected or {}).get("argument_ids",[])):flag("core_answer_inconsistent")
    if story["scqa"]["answer"]!=core["text"] or story["scqa"]["question"]!=story["decision_question"]:flag("scqa_inconsistent")
    for hypothesis in story["hypotheses"]:
        if not set(hypothesis["issue_ids"])<=set(issues):flag("hypothesis_issue_unresolved",hypothesis["hypothesis_id"])
        if hypothesis["status"]=="supported" and not hypothesis["evidence_ids"] or hypothesis["status"]=="refuted" and not hypothesis["counter_evidence_ids"]:flag("hypothesis_unproven",hypothesis["hypothesis_id"])
        for key in hypothesis["evidence_ids"]+hypothesis["counter_evidence_ids"]:
            if key not in graph.value["nodes"] or graph.value["nodes"][key]["status"]!="current":flag("hypothesis_evidence_unresolved",hypothesis["hypothesis_id"])
            elif not any(row["type"] in {"raw_fact","calculated_fact"} for row in graph.trace(key)):flag("hypothesis_unproven",hypothesis["hypothesis_id"])
    return {"passed":not any(row["severity"] in {"blocker","major"} for row in findings),"findings":findings}
