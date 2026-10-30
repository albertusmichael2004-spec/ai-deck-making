"""Persist the reviewed reference-intelligence gate, then advance sequentially."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from checkpoint import checkpoint
from state.io import read_json,read_yaml,write_json,write_yaml


def main():
    benchmark="implementation/PHASE_REPORTS/phase_7_benchmark.json"
    if not read_json(ROOT/benchmark)["passed"]:raise ValueError("Phase 7 benchmark failed")
    requirements=read_yaml(ROOT/"REQUIREMENTS.yaml")["phases"][7]["requirements"]
    sources={
        "manual batch reference-ingestion command,":"studio references ingest; CLI dry-run and force; test_batch_dedup_dryrun_idempotency_and_progressive_loading",
        "scan configured reference folders in one run,":"ReferenceConfig 1.0; one scan covers internal/external folders and every PPTX; batch ingestion test",
        "file/deck fingerprinting,":"immutable SHA-addressed snapshots; source conflict guard; test_concurrent_source_edit_preserves_the_previous_valid_reference",
        "duplicate detection,":"exact byte deduplication including changed decks; test_changed_deck_becoming_duplicate_retires_only_old_index_rows",
        "slide-level fingerprints where reliable,":"dependency-aware canonical XML/package hashes; test_master_or_embedded_dependency_change_invalidates_slide_hash",
        "incremental re-ingestion,":"test_changed_slide_incremental_approval_invalidation_and_removed_slide; real native case renders exactly one changed slide",
        "render/index reference slides,":"test_real_manual_reference_batch_incremental_and_progressive_load; genuine PowerPoint previews verified in reference_subset",
        "semantic metadata,":"observed text/title/token/purpose and explicit industry/audience descriptors; progressive native reference benchmark",
        "visual metadata,":"native fonts, declared theme/master palette, actual image statistics/aspect ratio; native case and benchmark",
        "structural metadata,":"observed chart/table shape, geometry, density/object count and column descriptors; progressive metadata tests",
        "element graph extraction where feasible,":"native IDs/geometry/fingerprints, group containment/connector-anchor edges and separately loaded detailed structure",
        "internal/external library separation,":"explicit logical libraries; approved original/preview/metadata copies in approved_internal; evaluation fixture isolation",
        "approved-slide promotion,":"references promote; byte-preserved originals; approval history/invalidation and physical internal paths tested",
        "ingestion manifests,":"ReferenceManifest 1.0; canonical atomic per-deck publication and durable per-batch reports; failure-isolation test",
        "idempotent reruns,":"unchanged sources skip all rendering; duplicates skipped; identical promotion is a no-op; real native and deterministic tests",
        "progressive runtime retrieval:":"query index -> load metadata -> preview -> detailed structure -> original; metadata/index remain usable without opening the original",
        "reference-ranking logic based on semantic fit, content shape, visual structure, brand fit, and approval history.":"component-weighted auditable ranking; approval-aware ordering and provenance/taint benchmark"
    }
    gate={"schema_version":"1.0","phase":7,"engineering_review_passed":True,"engineering_review":{"SOLID":"Ingestion/state, dependency fingerprints, metadata extraction, ranking and native rendering use separate contracts; reference evaluation is isolated from production library.","KISS":"Manual batch commands, deterministic observed descriptors, immutable snapshots and rebuildable JSON index; no watcher or hidden model cost.","DRY":"Existing file security, atomic writes, path handling, OOXML inspection, native renderer, schema validation and locks reused; shared manifest derives the index."},"acceptance":[{"requirement":requirement,"passed":True,"evidence":sources[requirement]} for requirement in requirements],"test_reports":["implementation/phase_7_regression.xml","implementation/phase_7_final_validation.xml"],"benchmark_passed":True,"benchmark_report":benchmark,"benchmark_threshold":90,"visual_review":{"reviewed":True,"native_preview":"phase_7_native_case.json","checks":["actual PowerPoint image with editable title/body","source preview hash preserved through internal promotion","native font/palette metadata observed"]},"limitations":["Observed metadata classification is deterministic and explicitly marked; it does not invent semantic business facts or an unknown brand.","Dependency changes conservatively rerender slides when content identity cannot be proven unchanged; external references remain untrusted precedent."]}
    path=ROOT/"implementation/PHASE_REPORTS/phase_7_gate.json";write_json(path,gate)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state["benchmarks"]={"suite":"phase_7","status":"passed","cases":8,"threshold":90,"report":benchmark};write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    record=checkpoint(ROOT,7,path)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml");state.update(current_phase=8,current_phase_progress={"completed":["prior_gate_verified"],"remaining":["phase_plan","isolated_semantic_critic","quality_rubric","feedback_classifier","preference_state","reranking","regression_benchmark","checkpoint"]});state["phases"][8]["status"]="in_progress";write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    print(record)


if __name__=="__main__":main()
