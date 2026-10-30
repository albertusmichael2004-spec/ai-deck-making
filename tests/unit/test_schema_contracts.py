from pathlib import Path

from jsonschema import Draft202012Validator

from state.io import read_json
from ir.validation import validate


def test_all_declared_schemas_are_valid():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "schemas").glob("*/*.json"):
        Draft202012Validator.check_schema(read_json(path))


def test_implementation_state_is_versioned_and_valid():
    from state.io import read_yaml
    root = Path(__file__).resolve().parents[2]
    validate(root, "implementation_state", read_yaml(root / "implementation/IMPLEMENTATION_STATUS.yaml"))
