from pathlib import Path

from qa.deterministic import DeterministicQA
from qa.media import image_ratios
from qa.regression import protected_scope
from qa.severity import report
from state.io import write_json
from presentation.rendering.preview import contact_sheet


class PresentationValidator:
    """Commit validator combines structure, real renders, layout and scope checks."""
    def __init__(self, repository, backend, renderer, output: Path, before=None, scope=None, allowed_overlaps=(),evidence=None,slide_specs=None):
        self.repository, self.backend, self.renderer, self.output = repository, backend, renderer, output
        self.before, self.scope, self.allowed_overlaps = before, scope, allowed_overlaps
        self.evidence,self.slide_specs=evidence,slide_specs

    def __call__(self, candidate):
        structural = self.backend.validate(candidate)
        if not structural["passed"]: return structural
        inspection = self.backend.inspect(candidate)
        rendered = self.renderer.render(candidate, self.output)
        qa = DeterministicQA(self.repository).check(inspection, rendered, self.allowed_overlaps, image_ratios(self.backend, candidate))
        issues = list(qa["issues"])
        if self.evidence is not None:
            self.evidence.assert_current()
            from qa.exhibits import data_exhibits
            issues.extend(data_exhibits(self.slide_specs,self.evidence,inspection,rendered))
        if self.before is not None:
            if self.scope is None:
                raise ValueError("Editing validator requires explicit scope")
            issues.extend(protected_scope(self.before, inspection, self.scope)["issues"])
        result = report(issues)
        result.update(rendered=True, structural_passed=True, renderer=rendered["renderer"], render_report=str(self.output / "render_report.json"))
        write_json(self.output / "qa_report.json", result)
        contact_sheet(rendered, self.output / "preview.png")
        return result
