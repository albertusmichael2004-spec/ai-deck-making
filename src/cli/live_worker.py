"""One terminal-owned STA for one bounded live command."""
import sys
from argparse import Namespace
from pathlib import Path

from cli.live_commands import execute_local
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json
from state.paths import repository_root
from security.paths import PathPolicy


def main(request,response):
    packet=read_json(Path(request));root=repository_root(Path(packet["root"]))
    policy=PathPolicy([root/"runtime/live_commands"],[root/"runtime/live_commands"])
    output=policy.check(Path(response),write=True);args=packet["args"]
    for key in ["root","target","request","output","copy_path"]:
        if args.get(key) is not None:args[key]=Path(args[key])
    try:write_json(output,{"result":execute_local(root,Namespace(**args))});return 0
    except StudioError as exc:write_json(output,{"error":exc.as_dict()});return 1
    except Exception as exc:
        error=StudioError(ErrorCode.LIVE_ATTACH_FAILED,"Live command failed; inspect retained transaction snapshots",exception_type=type(exc).__name__)
        write_json(output,{"error":error.as_dict()});return 1


if __name__=="__main__":raise SystemExit(main(*sys.argv[1:]))
