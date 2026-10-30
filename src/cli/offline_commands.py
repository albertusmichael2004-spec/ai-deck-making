from pathlib import Path


def add_parser(commands):
    parser=commands.add_parser("run")
    parser.add_argument("project_id")
    parser.add_argument("--request",type=Path,required=True)
    parser.add_argument("--resume")


def execute(root,args):
    from orchestration.pipeline import OfflinePipeline
    from research.provider import CodexProvider
    from state.io import read_json
    from state.project import Project
    project=Project.open(root,args.project_id)
    return OfflinePipeline(root,project,CodexProvider(root,180)).execute(read_json(project.policy.check(args.request)),run_id=args.resume)
