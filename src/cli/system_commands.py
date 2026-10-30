"""Installation status, capability profile and bootstrap verification commands."""
from state.io import read_yaml


def add_parser(commands):
    commands.add_parser("status")
    commands.add_parser("capabilities")
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--verify", action="store_true", required=True)


def execute(root, args):
    if args.command == "status":
        return read_yaml(root / "implementation/IMPLEMENTATION_STATUS.yaml")
    if args.command == "capabilities":
        return read_yaml(root / "config/capability_profiles/kernel.yaml")
    from knowledge.bootstrap import verify_bootstrap
    return verify_bootstrap(root)
