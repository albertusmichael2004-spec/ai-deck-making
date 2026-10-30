from pathlib import Path



def add_parser(commands):
    review=commands.add_parser("review");review.add_argument("project_id");review.add_argument("--spec",type=Path,required=True);review.add_argument("--render-report",type=Path,required=True);review.add_argument("--candidate",type=Path);review.add_argument("--output",type=Path,required=True);review.add_argument("--max-tokens",type=int,default=64000)
    feedback=commands.add_parser("feedback");feedback.add_argument("--request",type=Path,required=True)
    preferences=commands.add_parser("preferences");preferences.add_argument("action",choices=["status","reset","override"]);preferences.add_argument("--pattern");preferences.add_argument("--score",type=float);preferences.add_argument("--user-id",default="local");preferences.add_argument("--project-id",default="*");preferences.add_argument("--brand",default="*")


def execute(root,args):
    from preferences.store import PreferenceStore
    from state.io import read_json
    if args.command=="review":
        from evidence.context import EvidenceContext
        from evidence.store import EvidenceStore
        from knowledge.store import KnowledgeStore
        from presentation.backends.ooxml import OOXMLBackend
        from qa.critic import Critic
        from research.provider import CodexProvider
        from state.project import Project
        project=Project.open(root,args.project_id);candidate=project.policy.check(args.candidate or project.canonical);spec=read_json(project.policy.check(args.spec));rendered=read_json(project.policy.check(args.render_report));inspection=OOXMLBackend(root).inspect(candidate)
        return Critic(root,CodexProvider(root),KnowledgeStore(root)).evaluate(spec,candidate,inspection,rendered,EvidenceContext(EvidenceStore(root,project).load(),project.policy),output=project.policy.check(args.output,write=True),max_tokens=args.max_tokens)
    store=PreferenceStore(root)
    if args.command=="feedback":
        from security.paths import PathPolicy
        request=read_json(PathPolicy([root],[store.base]).check(args.request))
        from ir.validation import validate
        validate(root,"feedback_request",request);request.pop("schema_version",None)
        return store.record(**request)
    if args.action=="status":return store.state()
    if not args.pattern:
        from state.errors import StudioError,ErrorCode
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Preference change requires a pattern")
    context={"user_id":args.user_id,"project_id":args.project_id,"brand":args.brand}
    return store.reset(args.pattern,context=context) if args.action=="reset" else store.override(args.pattern,args.score,context=context)
