import importlib.util
from pathlib import Path


def test_empty_benchmark_cannot_pass():
    path = Path(__file__).resolve().parents[2] / "scripts/benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not module.run("empty", [])["passed"]
    def good(): return {"passed": True, "score": 100}
    def bad(): return {"passed": False, "score": 0}
    assert module.run("known", [good])["passed"]
    assert not module.run("known", [good, bad])["passed"]
