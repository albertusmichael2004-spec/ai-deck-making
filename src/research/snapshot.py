import base64

from research.documents import decode_document
from research.quality import validate_finding
from state.errors import StudioError,ErrorCode


def extract_snapshot(snapshot):
    document=snapshot["document"]
    try:raw=base64.b64decode(document["raw_base64"],validate=True)
    except ValueError as exc:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Research snapshot bytes are invalid") from exc
    decoded=decode_document(raw,document["mime"],document["url"])
    if any(decoded[key]!=document[key] for key in ["text","regions","sha256","text_sha256"]):
        raise StudioError(ErrorCode.SOURCE_CONFLICT,"Research snapshot differs from original source bytes")
    records=[]
    for index,finding in enumerate(snapshot["findings"]):
        validate_finding(finding,document)
        records.append({"locator":f"research:findings/{index}","value":finding["value"],"kind":"research_finding","quote":finding["quote"],"source_locator":finding["locator"],"url":document["url"],"original_sha256":document["sha256"]})
    return {"records":records,"limitations":[],"complete":True,"source_metadata":{"external_url":document["url"],"title":document.get("title",""),"publisher":snapshot.get("publisher","")}}
