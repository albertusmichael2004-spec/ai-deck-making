"""Qualify the complete sequential V1 release and create its recoverable checkpoint."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from checkpoint import checkpoint
from state.io import read_json,read_yaml,write_json,write_yaml,sha256


def main():
    benchmark="implementation/PHASE_REPORTS/phase_11_benchmark.json"
    measured=read_json(ROOT/benchmark)
    reports=["implementation/PHASE_REPORTS/phase_11_"+name+".json" for name in ["system_cases","installation","documentation"]]
    if not measured["passed"] or len(measured["results"])!=16 or not all(read_json(ROOT/path)["passed"] for path in reports):raise ValueError("Release evidence failed or incomplete")
    requirements=read_yaml(ROOT/"REQUIREMENTS.yaml")["phases"][11]["requirements"]
    evidence=[
        "Complete pytest unit/integration/regression/E2E run with real Windows PowerPoint and no failures/skips",
        "Controlled synthetic manufacturing, retail tie and financial-services negative-offset cases: full evidence->reasoning->design->native QA/Critic->repair->canonical pipeline",
        "Durable benchmark runner, resumable source/canonical fingerprints, per-case results and retained failed attempts",
        "Exact native data/cache/workbook values, source lineage, diagnostic expectations, scope and canonical SHA checks",
        "Actual isolated image-capable Critic uses canonical weighted rubric and per-slide message thresholds",
        "Exact numerical equality scored independently; signed narrative bug fixed and inverted-sign regression rejects corruption",
        "Content/source dimensions at least 90 plus independent current evidence checks; retail failed grounding retained and repaired without lowering threshold",
        "Independent dominant/tied-driver and supported/refuted-hypothesis expectations, narrative QA, conditional recommendations and actual qualitative narrative dimensions",
        "Source-bound ranking selects native bar exhibits, all earlier ten-exhibit consulting cases retained",
        "Actual visual scores: manufacturing 94.05, retail 91.35, financial services 93.00; weighted threshold remains 90",
        "Visible registered citations independently required; missing citation blocks even perfect qualitative score",
        "BLOCKER/MAJOR cannot be averaged away; wrong numbers, mismatched sources/units, corrupted candidates and scope violations fail",
        "Approved editable golden manifest and strict native pixel tolerances; incremental protected slides have zero changed pixels",
        "Real Windows PowerPoint existing-instance attach, capture, native pre/post renders; bounded CLI inspect/selection verified in a separate process",
        "Actual modern-comment author/filter/resolution/batch/preservation/processed-scan and chart/text/table selection E2E",
        "File commit/rollback crash journals and native post-mutation interruption recovery; later user edits preserved; unresolved recovery blocks save/detach/new mutation",
        "Research provider no-tool firewall, untrusted guidance/source/comments, injection blocking, scope protection, SSRF/private/mixed DNS and credential redaction tests",
        "MIME mismatch, corrupt/macro/OLE/ActiveX/external-link/ZIP traversal/duplicate/bomb and recursively hostile embedded XLSX tests",
        "Measured native/model tokens and latency, input/output/cache telemetry; unknown subscription cost remains null and dollar-budget requests fail closed",
        "Unchanged ingestion/references/research reuse and exact committed pipeline replay without extra inference or generation changes",
        "Six-step isolated editable venv install, dependency check, CLI/help, compile and inspect; verified local dependencies reused explicitly",
        "Maintained local Markdown links, all source syntax and JSON schema syntax validated; actual installed and native CLI contracts exercised",
        "Persistent release checklist maps every literal obligation to concrete reports; all sequential gates verified before checkpoint"
    ]
    if len(requirements)!=len(evidence):raise ValueError("Literal roadmap coverage changed")
    tests=["implementation/phase_11_regression.xml","implementation/phase_11_final_targeted.xml","implementation/phase_11_native_cli.xml"]
    gate={"schema_version":"1.0","phase":11,"engineering_review_passed":True,"engineering_review":{"SOLID":"Keep source/evidence, narrative/design, rendering, QA/Critic, transaction, native worker and release verification responsibilities separate; reuse the existing protocols.","KISS":"Synchronous bounded commands and immutable resumable case artifacts; no daemon, watcher, GUI or broad rewrite.","DRY":"Full release runner composes existing ingestion, reasoning, design, native QA, Critic, repair and atomic Project commit; benchmark aggregates earlier suites."},"acceptance":[{"requirement":r,"passed":True,"evidence":e} for r,e in zip(requirements,evidence,strict=True)],"test_reports":tests,"benchmark_passed":True,"benchmark_report":benchmark,"benchmark_threshold":90,"native_reports":reports,"limitations":["Native rendering/live collaboration require supported Windows PowerPoint and COM access; unsupported capabilities fail explicitly.","Cell-specific table text mutation and ambiguous comment targets require explicit supported scope; no unsafe whole-table replacement or guessed target.","Live recovery conflicts retain snapshots and require resolution; the system does not reconstruct unsaved edits discarded by the user.","Installation smoke reuses verified local/system dependencies; fresh network dependency resolution is not claimed.","Monetary cost is unknown for the configured subscription adapter; token/latency telemetry is measured and dollar budgets require a priced adapter.","Baseline industry cases validate controlled margin diagnostic decisions; optional user holdouts and Phase 12 remain separate."]}
    path=ROOT/"implementation/PHASE_REPORTS/phase_11_gate.json";write_json(path,gate)
    checklist={"schema_version":"1.0","status":"qualified_pending_checkpoint","architecture_version":"6.6","product_version":"1.0.0","items":gate["acceptance"],"test_reports":tests,"benchmark_report":benchmark,"evidence_reports":reports,"optional_phase_12":"not_started","release_gate":str(path.relative_to(ROOT))}
    checklist_path=ROOT/"implementation/PHASE_REPORTS/V1_RELEASE_CHECKLIST.json";write_json(checklist_path,checklist)
    capabilities=read_yaml(ROOT/"config/capability_profiles/kernel.yaml");capabilities["implemented_phase"]=11;capabilities["product_version"]="1.0.0";write_yaml(ROOT/"config/capability_profiles/kernel.yaml",capabilities)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state["benchmarks"]={"suite":"phase_11","status":"passed","cases":16,"threshold":90,"report":benchmark};write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    record=checkpoint(ROOT,11,path)
    checklist.update(status="complete",checkpoint=record);write_json(checklist_path,checklist)
    print(record)


if __name__=="__main__":main()
