from functools import lru_cache
from pathlib import Path
import json
import re

from urllib.parse import urlsplit, unquote
from state.errors import ErrorCode, StudioError
from state.io import read_json


@lru_cache(maxsize=64)
def _validator(schema_path: Path):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    schema = read_json(schema_path)
    schema["$id"]=schema_path.resolve().as_uri()
    Draft202012Validator.check_schema(schema)
    schema_root=schema_path.parents[1].resolve()
    def retrieve(uri):
        parsed=urlsplit(uri)
        if parsed.scheme!="file":raise StudioError(ErrorCode.SECURITY_BLOCK,"Schema references cannot access the network")
        value=unquote(parsed.path)
        if len(value)>2 and value[0]=="/" and value[2]==":":value=value[1:]
        path=Path(value).resolve()
        if not path.is_relative_to(schema_root):raise StudioError(ErrorCode.SECURITY_BLOCK,"Schema reference outside canonical schema root")
        return Resource.from_contents(read_json(path))
    return Draft202012Validator(schema,registry=Registry(retrieve=retrieve))


def validate(root: Path, name: str, value: dict):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Contract contains non-JSON or non-finite values") from exc
    if "/" in name or "\\" in name or name.startswith("."):
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Invalid schema name")
    version = value.get("schema_version", "1.0") if isinstance(value, dict) else "1.0"
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", version):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid schema version")
    path = root / "schemas" / name / (version + ".json")
    if not path.is_file():
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Schema is not implemented", schema=name)
    errors = sorted(_validator(path).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Schema validation failed", schema=name, errors=[{"path": list(e.absolute_path), "message": e.message} for e in errors])
