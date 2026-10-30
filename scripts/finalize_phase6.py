"""Record the reviewed Phase 6 gate and checkpoint after executable checks pass."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]

from checkpoint import checkpoint
from state.io import read_json,read_yaml,write_json,write_yaml


def main():
    benchmarks=["implementation/PHASE_REPORTS/phase_6_benchmark.json","implementation/PHASE_REPORTS/phase_6_consulting_benchmark.json"]
    if not all(read_json(ROOT/path)["passed"] for path in benchmarks):raise ValueError("Phase 6 benchmark failed")
    requirements=read_yaml(ROOT/"REQUIREMENTS.yaml")["phases"][6]["requirements"]
    evidence={
        "chart-selection logic,":"test_chart_selection_and_zero_crossing_waterfall_geometry; test_answer_first_storyline_to_source_bound_deck_is_idempotent",
        "core business charts,":"test_real_zero_crossing_bridge_and_core_chart_types (column/area/pie/stacked multi-series/scatter/bubble); test_native_consulting_exhibits_render_and_pass_qa (bar/line)",
        "waterfalls,":"test_native_consulting_exhibits_render_and_pass_qa; signed_bridge benchmark",
        "bridges,":"test_real_zero_crossing_bridge_and_core_chart_types; signed_bridge benchmark",
        "tables,":"test_research_snapshot_to_native_bound_table; research_provenance benchmark",
        "matrices,":"test_editable_charts_tables_diagrams_and_embedded_values; test_native_consulting_exhibits_render_and_pass_qa",
        "timelines,":"test_native_consulting_exhibits_render_and_pass_qa (explicit timeline fixture)",
        "issue trees,":"test_native_consulting_exhibits_render_and_pass_qa (native hierarchy and connectors)",
        "scenario exhibits,":"test_native_consulting_exhibits_render_and_pass_qa (conditional scenario fixture)",
        "recommendation exhibits,":"test_reasoning_to_native_consulting_deck_commit; supplied_storyline/template_storyline benchmarks (next steps/assumptions/tradeoffs visible)",
        "roadmap exhibits,":"test_native_consulting_exhibits_render_and_pass_qa",
        "chart annotation,":"test_native_consulting_exhibits_render_and_pass_qa (native reserved annotation strip)",
        "source-note placement,":"test_exhibit_note_coverage_and_nonpositive_bubble_sizes_rejected; research_provenance benchmark; native overflow QA",
        "brand profiles,":"BrandProfile 1.0; test_brand_grid_font_fallback_and_template_canvas_are_explicit",
        "grid systems,":"ConsultingLayout; native geometry/overlap checks; full retained baseline golden regression",
        "layout archetypes,":"native consulting fixture; answer-first single-exhibit and recommendation E2E decks",
        "adaptive layout compiler,":"test_answer_first_storyline_to_source_bound_deck_is_idempotent; native E2E using AdaptiveLayoutCompiler",
        "density management,":"test_binding_units_endpoint_and_density_are_mandatory; native overflow rejection; bounded table rows and two-line titles",
        "typography hierarchy,":"BrandProfile hierarchy validation; installed font fallback; native text/table/chart-label font checks",
        "design constraints and fallbacks.":"test_brand_grid_font_fallback_and_template_canvas_are_explicit; template byte preservation; incompatible canvas/unknown archetype fail explicitly"
    }
    gate={"schema_version":"1.0","phase":6,"engineering_review_passed":True,"engineering_review":{"SOLID":"Source resolver, storyline adapter, layout compiler, native business-object backend and independent native/source QA remain separate behind existing contracts.","KISS":"Manual explicit exhibit intents, native editable primitives and tokenized grids; no invented numeric labels or opaque service.","DRY":"EvidenceGraph lineage, source verification, shared waterfall math, schema validation, renderer and transaction gate reused; original template parts remain intact."},"acceptance":[{"requirement":requirement,"passed":True,"evidence":evidence[requirement]} for requirement in requirements],"test_reports":["implementation/phase_6_regression.xml","implementation/phase_6_final_validation.xml"],"benchmark_passed":True,"benchmark_reports":benchmarks,"benchmark_threshold":90,"visual_review":{"reviewed":True,"checks":["readable action titles and source notes","negative fills remain visible","scatter has unconnected markers","axis labels outside signed columns","recommendation assumptions/next steps visible","native tables have bounded row height"]},"limitations":["Phase 6 benchmark inputs are controlled fixtures; multi-industry release calibration and independent semantic Critic remain Phase 11 and Phase 8 obligations respectively.","Ambiguous aggregate/cross-source category associations fail until an explicit verified association contract is supplied; no label/value association is guessed."]}
    path=ROOT/"implementation/PHASE_REPORTS/phase_6_gate.json";write_json(path,gate)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml")
    state["benchmarks"]={"suite":"reasoning_subset + consulting_subset","status":"passed","cases":7,"threshold":90,"reports":benchmarks}
    write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    record=checkpoint(ROOT,6,path)
    state=read_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml")
    state.update(current_phase=7,current_phase_progress={"completed":["prior_gate_verified"],"remaining":["phase_plan","manual_batch_ingestion","incremental_fingerprints","native_previews_metadata","progressive_retrieval","approved_promotion","regression_benchmark","checkpoint"]})
    state["phases"][7]["status"]="in_progress"
    state["benchmarks"]={"suite":"reasoning_subset + consulting_subset","status":"passed","cases":7,"threshold":90,"reports":benchmarks}
    write_yaml(ROOT/"implementation/IMPLEMENTATION_STATUS.yaml",state)
    print(record)


if __name__=="__main__":main()
