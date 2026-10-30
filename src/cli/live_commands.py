from pathlib import Path
import os
import subprocess
import sys
from uuid import uuid4

from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json,read_yaml,logical_path


def add_parser(commands):
    parser=commands.add_parser("live")
    parser.add_argument("action",choices=["attach","inspect","selection","comments","plan-comments","apply-comments","apply","save","detach","recover"])
    parser.add_argument("project_id")
    parser.add_argument("--target",type=Path)
    parser.add_argument("--open-if-missing",action="store_true",default=True)
    parser.add_argument("--require-open",action="store_false",dest="open_if_missing")
    parser.add_argument("--save-policy",choices=["manual","save_copy","save_existing"])
    parser.add_argument("--copy-path",type=Path)
    parser.add_argument("--request",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--transaction-id")
    parser.add_argument("--author",action="append",default=[])
    parser.add_argument("--slide",action="append",default=[])
    parser.add_argument("--include-processed",action="store_true")
    parser.add_argument("--combine-selection",action="store_true")


def execute(root,args):
    """Bound native COM calls in an owned process; never terminate PowerPoint."""
    policy=read_yaml(root/"config/live/default.yaml")
    timeout=policy["command_timeout_seconds"]
    if type(timeout)!=int or not 30<=timeout<=1800:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid live command deadline")
    folder=root/"runtime/live_commands"/uuid4().hex;folder.mkdir(parents=True)
    packet={"root":str(root),"args":{key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()}}
    request=folder/"request.json";response=folder/"response.json";write_json(request,packet)
    env=os.environ.copy();env["PYTHONPATH"]=os.pathsep.join(str(Path(value).resolve()) for value in sys.path if value)
    try:
        result=subprocess.run([sys.executable,"-m","cli.live_worker",str(logical_path(request)),str(logical_path(response))],capture_output=True,text=True,timeout=timeout,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except subprocess.TimeoutExpired as exc:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Live command deadline reached; its worker stopped and PowerPoint/retained recovery snapshots remain intact",timeout_seconds=timeout,request=str(request)) from exc
    if not response.exists():raise StudioError(ErrorCode.LIVE_ATTACH_FAILED,"Live worker did not return a structured response; retained session/recovery state must be inspected",returncode=result.returncode)
    value=read_json(response)
    if "error" in value:
        error=value["error"];raise StudioError(ErrorCode(error["code"]),error["message"],**error.get("details",{}))
    if result.returncode:raise StudioError(ErrorCode.LIVE_ATTACH_FAILED,"Live worker failed after returning a response")
    return value["result"]


def execute_local(root,args):
    from knowledge.store import KnowledgeStore
    from presentation.live.batch import CommentBatch
    from presentation.live.paths import local_identity
    from presentation.live.session import LiveSession
    from presentation.live.windows import WindowsLiveBackend
    from qa.critic import Critic
    from research.provider import CodexProvider
    from state.project import Project
    project=Project.open(root,args.project_id);stored=project.path/"state/live_session.json"
    target=args.target
    if target is None:
        if stored.exists() and project.state()["authority"]=="live":target=Path(local_identity(read_json(stored)["target"]))
        else:target=project.canonical
    try:backend=WindowsLiveBackend.attach(root,target,open_if_missing=args.open_if_missing)
    except StudioError as exc:
        exc.details["safe_file_fallback"]={"allowed":project.state()["authority"]=="file","target":str(logical_path(project.canonical)),"policy":"Use scoped file revision on this same managed working target. Never create another working deck or substitute an unrelated active presentation."}
        raise
    session=LiveSession(root,project,backend)
    try:
        if args.action=="attach":result=session.attach(args.save_policy or "save_existing")
        else:
            session.state()
            request=read_json(project.policy.check(args.request)) if args.request else None
            if args.action=="inspect":result=backend.inspect()
            elif args.action=="selection":result=session.selection()
            elif args.action=="comments":
                from presentation.live.annotations import CommentLedger
                rows,capabilities=backend.comments();result={"capabilities":capabilities,"comments":CommentLedger(project).scan(rows,authors=args.author,slide_ids=args.slide,include_processed=args.include_processed)}
            elif args.action=="detach":result=session.detach()
            elif args.action=="recover":
                if not args.transaction_id:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Live recover requires transaction ID")
                result=session.recover(args.transaction_id)
            elif args.action=="save":
                if not args.save_policy:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Live save requires an explicit policy")
                result=session.save(args.save_policy,copy_path=args.copy_path)
            else:
                if request is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Live revision/comment planning requires a structured request")
                if args.action=="plan-comments":result=CommentBatch(root,session,None,None).plan(request["scope"],authors=args.author,slide_ids=args.slide,include_processed=args.include_processed,combine_selection=args.combine_selection)
                else:
                    provider=CodexProvider(root,240);critic=Critic(root,provider,KnowledgeStore(root))
                    if args.action=="apply-comments":result=CommentBatch(root,session,provider,critic).apply(request["plan"],request["spec"],copy_path=args.copy_path)
                    else:result=session.apply(request["patch"],request["scope"],request["spec"],critic,selection=request.get("selection"),copy_path=args.copy_path,transaction_id=args.transaction_id)
        if args.output:write_json(project.policy.check(args.output,write=True),result)
        return result
    finally:backend.release()
