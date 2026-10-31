from pathlib import Path


def add_parser(commands):
    parser=commands.add_parser("reason")
    parser.add_argument("project_id")
    parser.add_argument("--request",type=Path,required=True)
    parser.add_argument("--strategy",choices=["model","driver"],default="model")


def execute(root,args):
    from knowledge.store import KnowledgeStore
    from reasoning.engine import ReasoningEngine
    from research.provider import inference_provider
    from state.project import Project
    from state.io import read_json
    project=Project.open(root,args.project_id)
    request=read_json(project.policy.check(args.request))
    if args.strategy=="driver":
        from reasoning.strategies import DriverReasoningStrategy
        engine=ReasoningEngine(root,project,KnowledgeStore(root),strategy=DriverReasoningStrategy())
    else:engine=ReasoningEngine(root,project,KnowledgeStore(root),inference_provider(root))
    return engine.reason(**request)
