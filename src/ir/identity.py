import hashlib
from uuid import NAMESPACE_URL, uuid5


def object_id(deck_id: str, slide_id: str, role: str) -> str:
    return "obj_" + uuid5(NAMESPACE_URL, f"studio:{deck_id}:{slide_id}:{role}").hex


def numeric_id(identity: str) -> int:
    return 256 + int.from_bytes(hashlib.sha256(identity.encode()).digest()[:4], "big") % 2000000000
