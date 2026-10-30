from pathlib import Path

from evidence.verification import EvidenceVerifier
from state.errors import StudioError,ErrorCode
from state.io import fingerprint


class EvidenceContext:
    def __init__(self,graph,policy):
        self.graph,self.verifier=graph,EvidenceVerifier(policy)
        self.state_path=policy.read_roots[0]/"state/evidence_graph.json"
        self.state_fingerprint=fingerprint(self.state_path)

    def assert_current(self):
        if fingerprint(self.state_path)!=self.state_fingerprint:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence state changed during compilation/validation")

    def validate_slide(self,slide,sources_required):
        self.assert_current()
        if sources_required and not slide["claim_ids"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Evidence-required slide has no registered claim")
        sources=set()
        for identifier in slide["claim_ids"]:
            claim=self.graph.resolve(identifier)
            if claim["status"]!="current":raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Slide claim is stale or unverified")
            if claim["type"]=="hypothesis" and slide["purpose"]!="hypothesis":
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"A hypothesis must remain explicitly identified in the slide purpose")
            for node in self.graph.trace(identifier):
                if node["type"] in {"raw_fact","calculated_fact"}:self.verifier.value(self.graph,node["evidence_id"])
                if node["type"]=="raw_fact":sources.add(node["source_id"])
        if sources_required and (not sources or not sources<=set(slide["source_note_ids"])):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Slide source notes do not cover its claim lineage")
        return [self.source_note(source_id) for source_id in slide["source_note_ids"]]

    def source_note(self,source_id):
        if source_id not in self.graph.value["sources"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Source note refers to unknown source")
        source=self.graph.value["sources"][source_id]
        if source.get("external_url"):
            return "Source: "+(source.get("publisher") or source.get("title") or "Web source")+"; "+source["external_url"]+" ("+(source.get("data_period") or "period unspecified")+")"
        return "Source: "+Path(source["original_path"]).name+" ("+(source.get("data_period") or "period unspecified")+")"

    def resolve_exhibit(self,slide):
        self.assert_current()
        from evidence.exhibits import ExhibitResolver
        result=ExhibitResolver(self.graph,self.verifier.policy).resolve(slide)
        binding=self.graph.value["bindings"].get(slide["exhibit"].get("binding_id"))
        if binding:
            sources={node["source_id"] for key in binding["evidence_ids"] for node in self.graph.trace(key) if node["type"]=="raw_fact"}
            if not sources<=set(slide["source_note_ids"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Source notes do not cover the actual bound exhibit lineage")
        return result
