from pathlib import Path
from state.io import read_json,sha256
from state.project import Project
from evidence.context import EvidenceContext
from evidence.store import EvidenceStore
from presentation.backends.ooxml import OOXMLBackend
from qa.exhibits import data_exhibits


def cases(root):
    def representative_multi_industry_system():
        report=read_json(root/"implementation/PHASE_REPORTS/phase_11_system_cases.json")
        expected={"manufacturing","retail","financial_services"}
        for row in report["cases"]:
            project=Project.open(root,row["project_id"]);run=read_json(project.path/"work/offline_runs"/row["run_id"]/"run.json")
            spec=read_json(project.path/"work/offline_runs"/row["run_id"]/run["spec"])
            native=read_json(Path(row["review_directory"])/"render_report.json")
            inspection=OOXMLBackend(root).inspect(project.canonical)
            if native["input_sha256"]!=inspection["sha256"]:raise ValueError("Accepted native proof no longer matches canonical")
            findings=data_exhibits(spec["slides"],EvidenceContext(EvidenceStore(root,project).load(),project.policy),inspection,native)
            if findings:raise ValueError("Release data/citation hard-failure: "+str(findings))
        checks={"industry_coverage":{row["industry"] for row in report["cases"]}==expected,"quality_and_hard_failures":all(row["passed"] and all(row["checks"].values()) for row in report["cases"]),"actual_scores":all(row["scores"]["visual_quality"]>=90 for row in report["cases"]),"current_canonical":all(sha256(Project.open(root,row["project_id"]).canonical)==row["candidate_sha256"] for row in report["cases"]),"metered":all(row["tokens"]>0 and row["monetary_cost_usd"] is None for row in report["cases"])}
        return {"passed":report["passed"] and all(checks.values()),"score":min(row["scores"]["visual_quality"] for row in report["cases"]),"checks":checks,"cases":report["cases"]}
    def installation_setup():
        report=read_json(root/"implementation/PHASE_REPORTS/phase_11_installation.json")
        return {"passed":report["passed"] and all(row["passed"] for row in report["steps"]),"score":100 if report["passed"] else 0,"steps":report["steps"]}
    return [representative_multi_industry_system,installation_setup]
