

def add_parser(commands):
    parser=commands.add_parser("research")
    parser.add_argument("action",choices=["plan","run","status"])
    parser.add_argument("project_id")
    parser.add_argument("--request",type=__import__("pathlib").Path)
    parser.add_argument("--refresh",action="store_true")


def execute(root,args):
    from research.plan import ResearchPlanner
    from research.engine import ResearchEngine
    from research.fetch import PublicHTTPFetcher
    from research.provider import CodexProvider
    from state.project import Project
    from state.io import read_json
    project=Project.open(root,args.project_id)
    if args.action=="status":return read_json(project.path/"state/research/research_result.json")
    if args.request is None:
        from state.errors import StudioError,ErrorCode
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Research request is required")
    request=read_json(project.policy.check(args.request))
    plan=ResearchPlanner(root).plan(**request)
    if args.action=="plan":
        from research.state import ResearchState
        ResearchState(project).start(plan)
        return plan
    provider=CodexProvider(root)
    return ResearchEngine(root,project,provider,PublicHTTPFetcher(),provider).run(plan,refresh=args.refresh)
