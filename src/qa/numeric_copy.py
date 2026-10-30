"""Verify factual quantitative copy independently of the semantic reviewer."""
import re

from qa.severity import issue,Severity
from state.errors import StudioError

NUMBER=r"[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?"
CURRENCIES={"USD","IDR","EUR","GBP","JPY","CNY","INR","AUD","CAD","SGD","CHF","HKD","KRW","MYR","THB","NZD"}


def numeric_copy_findings(slides,evidence):
    findings=[]
    for slide in slides:
        if slide["purpose"]=="hypothesis":continue
        binding=evidence.graph.value["bindings"].get(slide["exhibit"].get("binding_id"),{})
        numeric=[];periods=set()
        for key in [*slide["claim_ids"],*binding.get("evidence_ids",[])]:
            for node in evidence.graph.trace(key):
                if node["type"] not in {"raw_fact","calculated_fact"}:continue
                try:
                    value=evidence.verifier.value(evidence.graph,node["evidence_id"])
                    if node.get("unit",{}).get("label") not in {"text","unspecified","identifier","category","year","period"} and re.fullmatch(NUMBER,str(value)):numeric.append(node["evidence_id"])
                    periods.update(re.findall(r"\b\d{4}\b",str(node.get("freshness",{}).get("data_period",""))))
                except StudioError:continue
        # Data labels are checked against native caches/workbooks elsewhere; this covers message copy.
        texts=[slide["action_title"],slide["key_message"],*slide.get("insights",[]),*[row["intent"] for row in slide.get("annotations",[])]]
        for item in slide["exhibit"].get("items",[]):texts.extend([item.get("title",""),item.get("body","")])
        for text in texts:
            for match in re.finditer(r"(?<![\w])("+NUMBER+r")(?![\w])",text):
                literal=match.group(1)
                if literal in periods:continue
                # Explicit proposed timeline/roadmap sequence markers are organizational labels.
                prefix=text[max(0,match.start()-8):match.start()].lower()
                if slide["exhibit"]["type"] in {"roadmap","timeline"} and re.search(r"(phase|stage|step|fase|tahap)\s*$",prefix):continue
                if slide["exhibit"]["type"] in {"roadmap","timeline","recommendation"} and len(literal)==4 and literal.isdigit() and 1900<=int(literal)<=2200 and re.search(r"(by|before|during|in|tahun|sebelum|pada)\s*$",prefix):continue
                supported=False
                before=text[max(0,match.start()-5):match.start()];after=text[match.end():]
                prefix_currency=re.search(r"\b([A-Z]{3})\s*$",before);suffix_currency=re.match(r"\s*([A-Z]{3})\b",after)
                marker=next((value.group(1) for value in [prefix_currency,suffix_currency] if value and value.group(1) in CURRENCIES),None)
                for key in numeric:
                    if text[match.end():].lstrip().startswith("%") and evidence.graph.resolve(key)["unit"]["label"].lower() not in {"%","percent","percentage","persen"}:continue
                    unit=evidence.graph.resolve(key)["unit"]
                    if marker and unit.get("currency",unit.get("label","").split(" ")[0])!=marker:continue
                    try:supported|=str(evidence.verifier.value(evidence.graph,key))==literal or evidence.verifier.displayed(evidence.graph,key,literal)
                    except StudioError:pass
                if not supported:findings.append(issue("UNREGISTERED_NUMERICAL_COPY",Severity.BLOCKER,slide["slide_id"],None,"Quantitative copy "+literal+" has no independently verified selected evidence"))
    return findings
