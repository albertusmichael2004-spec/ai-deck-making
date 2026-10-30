"""Deck file commands: OOXML compile/inspect/patch, native render/validate and project build/revise."""
from pathlib import Path

from state.errors import StudioError, ErrorCode
from state.io import read_json


def add_parser(commands):
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


def execute(root, args):
    if args.command == "probe-powerpoint":
        from presentation.backends.windows_probe import WindowsPowerPointProbe
        return WindowsPowerPointProbe().probe()
    from presentation.backends.ooxml import OOXMLBackend
    backend = OOXMLBackend(root)
    if args.command in {"compile", "inspect", "patch"}:
        return _ooxml(root, args, backend)
    from presentation.rendering.native import NativeRenderer
    renderer = NativeRenderer(root)
    if args.command == "render":
        return renderer.render(args.source, args.output)
    from qa.transaction import PresentationValidator
    if args.command == "validate":
        return PresentationValidator(root, backend, renderer, args.output)(args.source)
    return _project_transaction(root, args, backend, renderer)


def _ooxml(root, args, backend):
    if args.command == "compile":
        from presentation.compiler.compiler import PresentationCompiler
        from layout.adaptive import AdaptiveLayoutCompiler
        spec = read_json(backend.policy.check(args.spec))
        result = PresentationCompiler(root, AdaptiveLayoutCompiler(root), backend).compile(spec["brief"], spec["deck"], spec["slides"], args.output)
        result["rendered"] = False
        return result
    if args.command == "inspect":
        return backend.inspect(args.source)
    return backend.patch(args.source, args.output, read_json(backend.policy.check(args.patch)), read_json(backend.policy.check(args.scope)))


def _project_transaction(root, args, backend, renderer):
    """Build or revise a project's working deck inside one validated transaction."""
    from qa.transaction import PresentationValidator
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
            context, specs = _build_candidate(root, args, backend, project, transaction)
        else:
            before, scope = _revise_candidate(args, backend, project, transaction)
        validator = PresentationValidator(root, backend, renderer, output, before, scope, evidence=context, slide_specs=specs)
        result = project.commit(transaction, validator)
        return {"project": result, "rendered": True, "qa": read_json(output / "qa_report.json")}
    except Exception:
        journal = read_json(project.candidate(transaction).with_name("transaction.json"))
        if journal["status"] == "planned": project.abort(transaction)
        raise


def _build_candidate(root, args, backend, project, transaction):
    from layout.adaptive import AdaptiveLayoutCompiler
    from presentation.compiler.compiler import PresentationCompiler
    from preferences.store import PreferenceStore
    from evidence.store import EvidenceStore
    from evidence.context import EvidenceContext
    from state.io import write_json
    spec = read_json(backend.policy.check(args.spec))
    write_json(project.candidate(transaction).with_name("build_intent.json"), spec)
    context = EvidenceContext(EvidenceStore(root, project).load(), project.policy)
    layout = AdaptiveLayoutCompiler(root, PreferenceStore(root), {"user_id": "local", "project_id": args.project_id})
    PresentationCompiler(root, layout, backend).compile(spec["brief"], spec["deck"], spec["slides"], project.candidate(transaction), evidence=context)
    return context, spec["slides"]


def _revise_candidate(args, backend, project, transaction):
    from state.io import write_json
    before = backend.inspect(project.canonical)
    scope = read_json(backend.policy.check(args.scope))
    patch = read_json(backend.policy.check(args.patch))
    write_json(project.candidate(transaction).with_name("patch_intent.json"), {"patch": patch, "scope": scope})
    backend.patch(project.canonical, project.candidate(transaction), patch, scope)
    return before, scope
