"""Phase 0 result harness. Empty or unknown suites fail rather than pass vacuously."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def run(suite, cases):
    results = []
    for case in cases:
        try:
            result = case()
            passed = isinstance(result, dict) and result.get("passed") is True
            results.append({"case": case.__name__, "passed": passed, "result": result})
        except Exception as exc:
            results.append({"case": case.__name__, "passed": False, "error": str(exc)})
    return {"schema_version": "1.0", "suite": suite, "time": datetime.now(timezone.utc).isoformat(), "passed": bool(results) and all(r["passed"] for r in results), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases=[]
    if args.suite in {"reasoning_subset","consulting_subset","reference_subset","critic_subset","repair_subset","live_subset","system_subset","phase_7","phase_8","phase_9","phase_10","phase_11"}:
        import importlib.util
        root=Path(__file__).resolve().parents[1]
        suites=["reasoning_subset","consulting_subset","reference_subset",*( ["critic_subset"] if args.suite in {"phase_8","phase_9","phase_10","phase_11"} else []),*( ["repair_subset"] if args.suite in {"phase_9","phase_10","phase_11"} else []),*(["live_subset"] if args.suite in {"phase_10","phase_11"} else []),*(["system_subset"] if args.suite=="phase_11" else [])] if args.suite in {"phase_7","phase_8","phase_9","phase_10","phase_11"} else [args.suite]
        for suite in suites:
            spec=importlib.util.spec_from_file_location("studio_benchmark_"+suite,root/("tests/benchmarks/"+suite+".py"))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            cases.extend(module.cases(root))
    result = run(args.suite, cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)
