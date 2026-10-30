import argparse
import importlib
import json
from pathlib import Path
import sys

# Support Run Python File on this module as well as `python -m cli.main`.
if __name__ == '__main__' and not __package__:
    source_root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(source_root),str(source_root.parent/'runtime/python_packages')]

from state.errors import StudioError, ErrorCode
from state.paths import repository_root


# Each command module exposes add_parser(commands) and execute(root, args).
# Modules are listed in help order; dispatch imports only the selected one.
PARSER_MODULES = (
    "cli.system_commands",
    "cli.deck_commands",
    None,  # project/start parsers are registered here to keep help order
    "cli.data_commands",
    "cli.research_commands",
    "cli.knowledge_commands",
    "cli.reasoning_commands",
    "cli.design_commands",
    "cli.reference_commands",
    "cli.review_commands",
    "cli.offline_commands",
    "cli.live_commands",
)
COMMAND_MODULES = {
    **dict.fromkeys(["status", "capabilities", "bootstrap"], "cli.system_commands"),
    **dict.fromkeys(["compile", "inspect", "patch", "probe-powerpoint", "render", "validate", "build", "revise"], "cli.deck_commands"),
    "project": "cli.project_commands",
    "data": "cli.data_commands",
    "research": "cli.research_commands",
    "knowledge": "cli.knowledge_commands",
    "reason": "cli.reasoning_commands",
    "design": "cli.design_commands",
    **dict.fromkeys(["references", "database"], "cli.reference_commands"),
    **dict.fromkeys(["review", "feedback", "preferences"], "cli.review_commands"),
    "run": "cli.offline_commands",
    "live": "cli.live_commands",
}
WINDOWS_LOW_MEMORY_ERRORS = {8, 14, 1450, 1455}


def _add_project_parsers(commands):
    project = commands.add_parser("project")
    project.add_argument("action", nargs="?", choices=["create", "open", "snapshot", "rollback", "recover", "list", "use", "files", "import", "start", "others", "quick", "export"])
    project.add_argument("project_id", nargs="?")
    project.add_argument("--snapshot-id")
    project.add_argument("--source", type=Path, action="append")
    project.add_argument("--role", choices=["source", "asset", "target", "reference"], default="source")
    project.add_argument("--include-fixtures", action="store_true")
    commands.add_parser("start")


def build_parser():
    parser = argparse.ArgumentParser(prog="studio")
    parser.add_argument("--root", type=Path)
    commands = parser.add_subparsers(dest="command")
    for module in PARSER_MODULES:
        if module is None:
            _add_project_parsers(commands)
        else:
            importlib.import_module(module).add_parser(commands)
    return parser


def _resolve_root(explicit):
    try:
        return repository_root(explicit)
    except StudioError:
        if explicit is not None:raise
        # Editor shells can inherit System32. Resolve our own installation
        # only when no explicit root was supplied and cwd is outside a repo.
        return repository_root(Path(__file__).resolve().parents[2])


def _failed(result):
    return isinstance(result, dict) and result.get("passed") is False


def _error_payload(exc):
    if isinstance(exc, StudioError):
        return exc.as_dict()
    if isinstance(exc, MemoryError):
        return {"code":"USER_ACTION_REQUIRED","message":"Memory exhausted. Save work and close unused applications before retrying; the revision must still pass QA."}
    if getattr(exc,"winerror",None) in WINDOWS_LOW_MEMORY_ERRORS:
        return StudioError(ErrorCode.USER_ACTION_REQUIRED,"Windows has insufficient memory resources. Save work and close unused applications, then retry. No QA exception is needed.",os_error=exc.errno,winerror=exc.winerror).as_dict()
    return StudioError(ErrorCode.RETRYABLE, "Filesystem operation failed safely", os_error=exc.errno).as_dict()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        root = _resolve_root(args.root)
        if args.command is None or args.command == "start":
            from cli.workspace_menu import ProjectMenu
            return ProjectMenu(root).start_menu()
        result = importlib.import_module(COMMAND_MODULES[args.command]).execute(root, args)
        # Interactive menus report their own exit status instead of JSON.
        if isinstance(result, int):
            return result
        if getattr(args, "project_id", None) and not _failed(result):
            from state.outputs import export_others
            export_others(root, args.project_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if _failed(result) else 0
    except (StudioError, OSError, MemoryError) as exc:
        print(json.dumps(_error_payload(exc), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
