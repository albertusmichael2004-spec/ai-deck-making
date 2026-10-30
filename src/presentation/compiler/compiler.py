from pathlib import Path
from copy import deepcopy

from ir.validation import validate
from state.errors import ErrorCode, StudioError


class PresentationCompiler:
    def __init__(self, repository: Path, layout, backend):
        self.repository, self.layout, self.backend = repository, layout, backend

    def compile(self, brief: dict, deck: dict, slides: list[dict], destination: Path, evidence=None):
        validate(self.repository, "brief_spec", brief)
        validate(self.repository, "deck_spec", deck)
        if deck["brief_id"] != brief["brief_id"] or len(slides) > brief["page_budget"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Brief identity or page budget mismatch")
        template=deck.get("template")
        if brief["constraints"]["use_existing_template"] and not template:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Template-constrained brief requires an explicit registered template/layout")
        if template and not brief["constraints"]["use_existing_template"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Template was supplied without a matching brief constraint")
        if [s.get("slide_id") for s in slides] != deck["slide_ids"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Slide ordering does not match DeckSpec")
        compiled = []
        for slide in slides:
            validate(self.repository, "slide_spec", slide)
            if evidence is None and (slide["claim_ids"] or slide["source_note_ids"] or brief["constraints"]["sources_required"]):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Evidence-grounded compilation requires a validated evidence context")
            notes=evidence.validate_slide(slide,brief["constraints"]["sources_required"]) if evidence is not None else []
            prepared=deepcopy(slide)
            if slide["exhibit"]["type"] not in {"text","shapes","timeline","roadmap","issue_tree","scenario","recommendation"}:
                if evidence is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Data exhibits require a validated evidence context")
                prepared["exhibit"]=evidence.resolve_exhibit(slide)
            result = self.layout.compile(deck, prepared, source_notes=notes)
            for item in result["objects"]:
                validate(self.repository, "object_spec", item)
            compiled.append(result)
        if template:return self.backend.create(compiled,deck["canvas"],destination,template=template)
        return self.backend.create(compiled, deck["canvas"], destination)
