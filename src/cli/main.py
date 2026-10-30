import argparse
import json
from pathlib import Path
import sys

# Support Run Python File on this module as well as `python -m cli.main`.
if __name__ == '__main__' and not __package__:
    source_root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(source_root),str(source_root.parent/'runtime/python_packages')]

from state.errors import StudioError, ErrorCode
from state.io import read_yaml, read_json
from state.paths import initialize_folders, repository_root


def main(argv=None):
    parser = argparse.ArgumentParser(prog="studio")
    parser.add_argument("--root", type=Path)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("status")
    commands.add_parser("capabilities")
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--verify", action="store_true", required=True)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--spec", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("source", type=Path)
    patch_command = commands.add_parser("patch")
    patch_command.add_argument("source", type=Path)
    patch_command.add_argument("--patch", type=Path, required=True)
    patch_command.add_argument("--scope", type=Path, required=True)
    patch_command.add_argument("--output", type=Path, required=True)
    commands.add_parser("probe-powerpoint")
    render_command = commands.add_parser("render")
    render_command.add_argument("source", type=Path)
    render_command.add_argument("--output", type=Path, required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("source", type=Path)
    validate_command.add_argument("--output", type=Path, required=True)
    build_command = commands.add_parser("build")
    build_command.add_argument("project_id")
    build_command.add_argument("--spec", type=Path, required=True)
    revise_command = commands.add_parser("revise")
    revise_command.add_argument("project_id")
    revise_command.add_argument("--patch", type=Path, required=True)
    revise_command.add_argument("--scope", type=Path, required=True)
    project = commands.add_parser("project")
    project.add_argument("action", nargs="?", choices=["create", "open", "snapshot", "rollback", "recover", "list", "use", "files", "import", "start", "others", "quick", "export"])
    project.add_argument("project_id", nargs="?")
    project.add_argument("--snapshot-id")
    project.add_argument("--source", type=Path, action="append")
    project.add_argument("--role", choices=["source", "asset", "target", "reference"], default="source")
    project.add_argument("--include-fixtures", action="store_true")
    commands.add_parser("start")
    from cli.data_commands import add_parser
    add_parser(commands)
    from cli.research_commands import add_parser as research_parser
    research_parser(commands)
    from cli.knowledge_commands import add_parser as knowledge_parser
    knowledge_parser(commands)
    from cli.reasoning_commands import add_parser as reasoning_parser
    reasoning_parser(commands)
    from cli.design_commands import add_parser as design_parser
    design_parser(commands)
    from cli.reference_commands import add_parser as reference_parser
    reference_parser(commands)
    from cli.review_commands import add_parser as review_parser
    review_parser(commands)
    from cli.offline_commands import add_parser as offline_parser
    offline_parser(commands)
    from cli.live_commands import add_parser as live_parser
    live_parser(commands)
    args = parser.parse_args(argv)
    try:
        try:
            root = repository_root(args.root)
        except StudioError:
            if args.root is not None:raise
            # Editor shells can inherit System32. Resolve our own installation
            # only when no explicit root was supplied and cwd is outside a repo.
            root = repository_root(Path(__file__).resolve().parents[2])
        if args.command is None or args.command == "start":
            from cli.workspace_menu import ProjectMenu
            return ProjectMenu(root).start_menu()
        elif args.command == "project" and args.action in {None, "list", "use", "files", "import", "start", "others", "quick", "export"}:
            from cli.project_commands import execute
            result = execute(root, args)
            if isinstance(result, int):
                return result
        elif args.command == "status":
            result = read_yaml(root / "implementation/IMPLEMENTATION_STATUS.yaml")
        elif args.command == "capabilities":
            result = read_yaml(root / "config/capability_profiles/kernel.yaml")
        elif args.command == "bootstrap":
            from knowledge.bootstrap import verify_bootstrap
            result = verify_bootstrap(root)
        elif args.command == "data":
            from cli.data_commands import execute
            result = execute(root,args)
        elif args.command == "research":
            from cli.research_commands import execute
            result = execute(root,args)
        elif args.command == "knowledge":
            from cli.knowledge_commands import execute
            result = execute(root,args)
        elif args.command == "reason":
            from cli.reasoning_commands import execute
            result = execute(root,args)
        elif args.command == "design":
            from cli.design_commands import execute
            result = execute(root,args)
        elif args.command in {"references", "database"}:
            from cli.reference_commands import execute
            result = execute(root,args)
        elif args.command in {"review","feedback","preferences"}:
            from cli.review_commands import execute
            result = execute(root,args)
        elif args.command == "run":
            from cli.offline_commands import execute
            result = execute(root,args)
        elif args.command == "live":
            from cli.live_commands import execute
            result = execute(root,args)
        elif args.command in {"compile", "inspect", "patch"}:
            from presentation.backends.ooxml import OOXMLBackend
            backend = OOXMLBackend(root)
            if args.command == "compile":
                from presentation.compiler.compiler import PresentationCompiler
                from layout.adaptive import AdaptiveLayoutCompiler
                spec = read_json(backend.policy.check(args.spec))
                result = PresentationCompiler(root, AdaptiveLayoutCompiler(root), backend).compile(spec["brief"], spec["deck"], spec["slides"], args.output)
                result["rendered"] = False
            elif args.command == "inspect":
                result = backend.inspect(args.source)
            else:
                result = backend.patch(args.source, args.output, read_json(backend.policy.check(args.patch)), read_json(backend.policy.check(args.scope)))
        elif args.command == "probe-powerpoint":
            from presentation.backends.windows_probe import WindowsPowerPointProbe
            result = WindowsPowerPointProbe().probe()
        elif args.command in {"render", "validate", "build", "revise"}:
            from presentation.backends.ooxml import OOXMLBackend
            from presentation.rendering.native import NativeRenderer
            from qa.transaction import PresentationValidator
            from state.io import write_json
            backend, renderer = OOXMLBackend(root), NativeRenderer(root)
            if args.command == "render":
                result = renderer.render(args.source, args.output)
            elif args.command == "validate":
                result = PresentationValidator(root, backend, renderer, args.output)(args.source)
            else:
                from state.project import Project
                project = Project.open(root, args.project_id)
                if args.command == "build" and project.canonical.exists():
                    raise StudioError(ErrorCode.FILE_CONFLICT, "A working deck already exists; use a scoped revision")
                transaction = project.begin()
                output = project.path / "work/transactions" / transaction / "renders"
                before, scope = None, None
                context, specs = None, None
                try:
                    if args.command == "build":
                        from layout.adaptive import AdaptiveLayoutCompiler
                        from presentation.compiler.compiler import PresentationCompiler
                        from preferences.store import PreferenceStore
                        spec = read_json(backend.policy.check(args.spec))
                        specs=spec["slides"]
                        write_json(project.candidate(transaction).with_name("build_intent.json"), spec)
                        from evidence.store import EvidenceStore
                        from evidence.context import EvidenceContext
                        context=EvidenceContext(EvidenceStore(root,project).load(),project.policy)
                        layout=AdaptiveLayoutCompiler(root,PreferenceStore(root),{"user_id":"local","project_id":args.project_id})
                        PresentationCompiler(root,layout,backend).compile(spec["brief"], spec["deck"], spec["slides"], project.candidate(transaction),evidence=context)
                    else:
                        before = backend.inspect(project.canonical)
                        scope = read_json(backend.policy.check(args.scope))
                        patch = read_json(backend.policy.check(args.patch))
                        write_json(project.candidate(transaction).with_name("patch_intent.json"), {"patch": patch, "scope": scope})
                        backend.patch(project.canonical, project.candidate(transaction), patch, scope)
                    validator = PresentationValidator(root, backend, renderer, output, before, scope,evidence=context,slide_specs=specs)
                    result = project.commit(transaction, validator)
                    result = {"project": result, "rendered": True, "qa": read_json(output / "qa_report.json")}
                except Exception:
                    journal = read_json(project.candidate(transaction).with_name("transaction.json"))
                    if journal["status"] == "planned": project.abort(transaction)
                    raise
        else:
            from state.project import Project
            if not args.project_id:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "This project action requires a project ID")
            initialize_folders(root)
            project = Project.create(root, args.project_id) if args.action == "create" else Project.open(root, args.project_id)
            if args.action == "rollback":
                if not args.snapshot_id:
                    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Rollback requires --snapshot-id")
                from uuid import uuid4
                from presentation.backends.ooxml import OOXMLBackend
                from presentation.rendering.native import NativeRenderer
                from qa.transaction import PresentationValidator
                validator = PresentationValidator(root, OOXMLBackend(root), NativeRenderer(root), project.path / "work/temp" / ("rollback_render_" + uuid4().hex))
                result = project.rollback(args.snapshot_id, project.token(), validator)
            else:
                result = project.snapshot() if args.action == "snapshot" else project.recover() if args.action == "recover" else project.state()
        if getattr(args, "project_id", None) and not (isinstance(result, dict) and result.get("passed") is False):
            from state.outputs import export_others
            export_others(root, args.project_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if isinstance(result, dict) and result.get("passed") is False else 0
    except StudioError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False))
        return 1
    except OSError as exc:
        if getattr(exc,"winerror",None) in {8,14,1450,1455}:
            error=StudioError(ErrorCode.USER_ACTION_REQUIRED,"Windows has insufficient memory resources. Save work and close unused applications, then retry. No QA exception is needed.",os_error=exc.errno,winerror=exc.winerror)
        else:
            error = StudioError(ErrorCode.RETRYABLE, "Filesystem operation failed safely", os_error=exc.errno)
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 1
    except MemoryError:
        print(json.dumps({"code":"USER_ACTION_REQUIRED","message":"Memory exhausted. Save work and close unused applications before retrying; the revision must still pass QA."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
