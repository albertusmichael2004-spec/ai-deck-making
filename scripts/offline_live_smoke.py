"""Measured native repair loop over an explicitly corrupted owned fixture."""
import sys
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"runtime/python_packages")]
from knowledge.store import KnowledgeStore
from layout.adaptive import AdaptiveLayoutCompiler
from orchestration.offline import OfflineLoop
from presentation.backends.ooxml import OOXMLBackend
from presentation.rendering.native import NativeRenderer
from qa.critic import Critic
from research.provider import CodexProvider
from state.errors import StudioError
from state.io import read_json,write_json
from state.project import Project


class CorruptedFixtureLayout(AdaptiveLayoutCompiler):
    def compile(self,deck,slide,source_notes=()):
        result=super().compile(deck,slide,source_notes=source_notes)
        if slide["purpose"]=="executive_summary":
            next(obj for obj in result["objects"] if obj["role"]=="title")["text"]="Recover 99 percentage points of margin."
        return result


def main(resume=None):
    measured=read_json(ROOT/"implementation/PHASE_REPORTS/phase_8_live_smoke.json")
    project=Project.open(ROOT,measured["project_id"])
    if project.canonical.exists():raise ValueError("Owned diagnostic project is already committed; inspect the recorded run rather than overwrite")
    spec=read_json(project.path/"state/design_spec.json");provider=CodexProvider(ROOT,240)
    loop=OfflineLoop(ROOT,project,OOXMLBackend(ROOT),NativeRenderer(ROOT),Critic(ROOT,provider,KnowledgeStore(ROOT)),layout=CorruptedFixtureLayout(ROOT))
    result=loop.run(spec,max_iterations=3,max_seconds=900,max_tokens=192000,run_id=resume)
    result.update(fixture=True,corruption="Visible executive title intentionally contains unsupported 99; trusted IR/evidence remain unchanged",project_id=project.path.name)
    write_json(ROOT/"implementation/PHASE_REPORTS/phase_9_live_smoke.json",result)
    print({"passed":result["passed"],"run_id":result["run_id"],"iterations":result["state"]["iteration"],"tokens":result["state"]["tokens"],"stop_reason":result["state"].get("stop_reason"),"history":result["state"]["history"]})
    return 0 if result["passed"] else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--resume");args=parser.parse_args()
    try:raise SystemExit(main(args.resume))
    except StudioError as exc:print(exc.as_dict());raise SystemExit(1)
