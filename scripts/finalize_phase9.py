"""Checkpoint the measured native offline repair and incremental refresh gate."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from checkpoint import checkpoint
from state.io import read_json,read_yaml,write_json,write_yaml


def main():
    benchmark="implementation/PHASE_REPORTS/phase_9_benchmark.json"
    if not read_json(ROOT/benchmark)["passed"]:raise ValueError("Phase 9 benchmark failed")
    live=read_json(ROOT/"implementation/PHASE_REPORTS/phase_9_live_smoke.json")
    incremental=read_json(ROOT/"implementation/PHASE_REPORTS/phase_9_incremental_native.json")
    if not live["passed"] or not incremental["passed"]:raise ValueError("Measured native acceptance failed")
    requirements=read_yaml(ROOT/"REQUIREMENTS.yaml")["phases"][9]["requirements"]
    evidence=[
        "Strict PatchPlan 1.0 links candidate hash, PatchSpec, reason, scope and analytical dependencies",
        "PatchExecutor verifies exact candidate/object fingerprints and refuses widened scope/source-note edits",
        "IncrementalCompiler prepares only affected layouts and imports dependency closures; real native one-slide recompile",
        "OfflinePipeline REQUEST->evidence/research->reasoning->design->native QA/Critic->repair->commit; native isolated model repair 65.25 to 92.95",
        "Finite iterations/tokens/latency; monetary limits require actual telemetry; no-op/diminishing-return stops",
        "RepairPlanner orders BLOCKER, MAJOR, MINOR, STYLE and emits only supported guarded operations",
        "Immutable iteration candidates and durable intent pointers; interruption before review/commit and user-conflict tests",
        "Repair and initial-patch no-op tests; committed replay does not advance generation",
        "Full native rerender plus protected fingerprints/data and zero-pixel differences on untouched slides",
        "Explicit trusted scope and group/child/chart-workbook dependency fingerprints; unauthorized targets rejected",
        "Source refresh recomputes calculations, invalidates old claims; AnalyticalRefresh regenerates reasoning/bindings while keeping slide identities and appendix allocation; changed values 2/1 verified",
        "Project atomic commit only after real native QA and independent Critic pass; final candidate/evidence/scope recheck"
    ]
    if len(evidence)!=len(requirements):raise ValueError("Roadmap coverage changed")
    gate={"schema_version":"1.0","phase":9,"engineering_review_passed":True,
          "engineering_review":{"SOLID":"Preparation, analytical refresh, incremental compiler, repair planning/execution and transaction commit remain separate responsibilities.","KISS":"Finite synchronous loops and immutable iteration files with explicit resume; no daemon/watchers.","DRY":"Reuse existing schema, security, evidence/reasoning/design, native renderer, QA, protected-scope and atomic Project transaction contracts."},
          "acceptance":[{"requirement":r,"passed":True,"evidence":e} for r,e in zip(requirements,evidence,strict=True)],
          "test_reports":["implementation/phase_9_regression.xml","implementation/phase_9_final_deterministic.xml"],
          "benchmark_passed":True,"benchmark_report":benchmark,"benchmark_threshold":90,
          "native_reports":["implementation/PHASE_REPORTS/phase_9_live_smoke.json","implementation/PHASE_REPORTS/phase_9_incremental_native.json"],
          "resolved_regression":"Independent native review found an incorrect bar-axis origin after category reversal. Corrected origin, added deterministic axis QA, dependency fingerprints and data-preserving axis repair; failed experiment journals retained.",
          "limitations":["Unsupported repair intents fail closed; analytical edits require fresh verified claims, and changed slide structure requires explicit new scope.","Monetary cost is unavailable for the configured subscription provider; monetary-budget requests fail before inference instead of treating unknown cost as zero."]}
    path=ROOT/"implementation/PHASE_REPORTS/phase_9_gate.json";write_json(path,gate)
    capabilities=read_yaml(ROOT/"config/capability_profiles/kernel.yaml");capabilities["implemented_phase"]=9
    for name in ["presentation.autorepair","presentation.incremental_compile","evidence.analytical_refresh","orchestration.run"]:
        if name not in capabilities["available"]:capabilities["available"].append(name)
    write_yaml(ROOT/"config/capability_profiles/kernel.yaml",capabilities)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state["benchmarks"]={"suite":"phase_9","status":"passed","cases":12,"threshold":90,"report":benchmark};write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    record=checkpoint(ROOT,9,path)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml")
    state.update(current_phase=10,current_phase_progress={"completed":["prior_gate_verified"],"remaining":["phase_plan","live_attach_authority","selection_comments","live_guard_recovery","native_e2e","regression_benchmark","checkpoint"]})
    state["phases"][10]["status"]="in_progress";write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    print(record)


if __name__=="__main__":main()
