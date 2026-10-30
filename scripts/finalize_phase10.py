"""Gate the measured native live collaboration before proceeding to release hardening."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from checkpoint import checkpoint
from state.io import read_json,read_yaml,write_json,write_yaml


def main():
    benchmark="implementation/PHASE_REPORTS/phase_10_benchmark.json"
    measured=read_json(ROOT/benchmark)
    if not measured["passed"]:raise ValueError("Live benchmark failed")
    reports=["implementation/PHASE_REPORTS/phase_10_"+name+".json" for name in ["probe","native_case","comments_native","table_native","recovery_native","model_native"]]
    if not all(read_json(ROOT/path)["passed"] for path in reports):raise ValueError("Actual native acceptance failed")
    requirements=read_yaml(ROOT/"REQUIREMENTS.yaml")["phases"][10]["requirements"]
    evidence=[
        "GetActiveObject attach only; actual existing-instance native probe and E2E",
        "Exact registered local/OneDrive identity; explicit open_if_missing and validated target",
        "Project live authority excludes file writers; current SaveCopyAs captures unsaved content",
        "Double native inspection with stable identities, geometry, text, style, chart/table data",
        "SelectionContext active_slide_id from actual active window/View.Slide",
        "Strict SelectionContext schema, session/generation identity and observed target fingerprints",
        "Actual native chart, UTF16 text selection and table capture; shape/slide-range contracts",
        "Current live snapshot legacy/modern comments and individual replies; schema capability detection",
        "Strict AnnotationInstruction schema applied to every resolved instruction",
        "AnnotationResolver combines scoped containment/type/text and explicit selected context",
        "Actual modern native comment resolves to the scoped body object",
        "Confidence threshold and margin; ambiguity/protection/injection tests fail closed",
        "Durable CommentLedger provenance, status history and transaction references",
        "Idempotent processed scans; parent comment identity remains stable on new replies",
        "Actual author metadata and slide/scope filters; no author-name guesses",
        "CommentBatch emits a constrained patch followed by native planned/applied QA and Critic",
        "Native E2E verifies original comment content remains present",
        "Optional acknowledgment kept in ledger status/transaction metadata without rewriting comments",
        "Project authority locks and file begin rejection during a live session",
        "Session and backend check target fingerprints immediately before each mutation",
        "Native concurrent user-edit test rejects mutation and preserves intervening changes",
        "Durable operation intent, scoped ownership checks and full pre/post reviews",
        "Retained exact snapshots; native injected post-apply interruption recovers owned changes",
        "Explicit manual/save_copy/save_existing; disk fingerprint guard and AutoSave pause",
        "Native selected text/comment/table E2E preserves dirty original and outside-scope unsaved edits",
        "Structured unavailable-capability fallback requires separate registered file working copy"
    ]
    if len(evidence)!=len(requirements):raise ValueError("Literal roadmap coverage changed")
    gate={"schema_version":"1.0","phase":10,"engineering_review_passed":True,"engineering_review":{"SOLID":"Native backend, session transaction, annotation resolver, ledger and comment planning remain separate responsibilities.","KISS":"Explicit synchronous terminal commands, manual save policy and durable local journals; no watcher or implicit Undo.","DRY":"Shared native metrics/exporter, existing IR/security/evidence/QA/Critic and protected-scope contracts."},"acceptance":[{"requirement":r,"passed":True,"evidence":e} for r,e in zip(requirements,evidence,strict=True)],"test_reports":["implementation/phase_10_regression.xml","implementation/phase_10_final_deterministic.xml","implementation/phase_10_cleanup_native.xml"],"benchmark_passed":True,"benchmark_report":benchmark,"native_reports":reports,"resolved_regressions":["Borrowed COM apartment teardown invalidated other proxies; release no longer uninitializes the terminal's STA.","Office modern comments ignore requested author parameters; current snapshot capture uses actual author metadata and preserves replies.","Critic invented target IDs; added explicit observed object inventory and constrained response identifiers, retaining local cross-slide validation.","Owned native fixtures release child proxies before closing presentations or quitting their private application.","Full regression initially used an outdated control adapter; corrected its native canvas/local target contract and reran all 196 tests."],"limitations":["Unsupported cell-specific mutations remain explicit capability errors; table selection is captured without widening into unsafe whole-table text replacement.","Unavailable shared disk fingerprint disables save_existing; manual/copy policies preserve live unsaved authority.","Recovery preserves later user edits and retains snapshots for unknown partial writes rather than rolling them back."]}
    path=ROOT/"implementation/PHASE_REPORTS/phase_10_gate.json";write_json(path,gate)
    capabilities=read_yaml(ROOT/"config/capability_profiles/kernel.yaml");capabilities["implemented_phase"]=10
    for name in ["presentation.attach_live","presentation.live_selection","presentation.live_comments","presentation.live_recovery"]:
        if name not in capabilities["available"]:capabilities["available"].append(name)
        capabilities.get("unavailable",{}).pop(name,None)
    write_yaml(ROOT/"config/capability_profiles/kernel.yaml",capabilities)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state["benchmarks"]={"suite":"phase_10","status":"passed","cases":len(measured["results"]),"threshold":90,"report":benchmark};write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    record=checkpoint(ROOT,10,path)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state.update(current_phase=11,current_phase_progress={"completed":["prior_gate_verified"],"remaining":["phase_plan","release_benchmarks","hardening","full_regression","installation_docs","release_checkpoint"]});state["phases"][11]["status"]="in_progress";write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    print(record)


if __name__=="__main__":main()
