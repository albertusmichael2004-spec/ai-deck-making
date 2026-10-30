from collections import defaultdict

from state.errors import StudioError,ErrorCode


def tree_positions(items,x,y,width,height,gutter):
    identifiers={item["id"]:item for item in items}
    if len(identifiers)!=len(items):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Duplicate issue-tree node")
    depth={};levels=defaultdict(list)
    def visit(identifier,seen):
        if identifier in seen:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Issue-tree cycle")
        if identifier in depth:return depth[identifier]
        parent=identifiers[identifier].get("parent_id")
        if parent is not None and parent not in identifiers:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Issue-tree parent is absent")
        depth[identifier]=0 if parent is None else visit(parent,{*seen,identifier})+1
        return depth[identifier]
    for identifier in identifiers:levels[visit(identifier,set())].append(identifier)
    rows=max(levels)+1;row_h=(height-gutter*(rows-1))/rows
    if row_h<.75:raise StudioError(ErrorCode.QA_FAILURE,"Issue-tree depth exceeds a readable grid")
    positions={}
    for level,values in levels.items():
        cell_w=(width-gutter*(len(values)-1))/len(values)
        for index,identifier in enumerate(values):positions[identifier]={"x":x+index*(cell_w+gutter),"y":y+level*(row_h+gutter),"width":cell_w,"height":row_h}
    return positions
