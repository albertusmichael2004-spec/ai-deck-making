import re

from state.errors import StudioError,ErrorCode


def record_key(node):
    locator=node.get("locator","")
    if "/column:" in locator:return locator.split("/column:",1)[0]
    if locator.startswith("sheet:") and "!" in locator:
        sheet,cell=locator.rsplit("!",1);matched=re.fullmatch(r"[A-Z]+([0-9]+)",cell)
        if matched:return sheet+"/row:"+matched[1]
    if locator.startswith("$") and "/" in locator:return locator.rsplit("/",1)[0]
    return locator


def verify_association(graph,category_id,quantity_id):
    category=graph.resolve(category_id)
    lineage=[node for node in graph.trace(quantity_id) if node["type"]=="raw_fact"]
    if not any(node.get("source_id")==category.get("source_id") and record_key(node)==record_key(category) for node in lineage):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Category and quantity do not share a verified source record",category=category_id,quantity=quantity_id)
