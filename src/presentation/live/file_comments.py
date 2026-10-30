"""Read legacy/modern comments from an exact current SaveCopyAs snapshot."""
import posixpath
from copy import deepcopy

from presentation.backends.xml import NS,parse
from presentation.live.inspection import digest
from state.errors import StudioError,ErrorCode

MODERN="http://schemas.microsoft.com/office/powerpoint/2018/8/main"
DRAWING=NS["a"]


def visible_text(node,namespace):
    body=node.find("{"+namespace+"}txBody")
    if body is None:return node.findtext("{"+namespace+"}text",default="")
    return "\n".join("".join(text.text or "" for text in paragraph.findall(".//{"+DRAWING+"}t")) for paragraph in body.findall("{"+DRAWING+"}p"))


def read_comments(backend,source):
    package=backend._read(source);authors={};legacy={}
    for name,(_,data) in package.items():
        if name.endswith(".xml") and name.startswith("ppt/") and (name.endswith("authors.xml") or name.endswith("commentAuthors.xml")):
            for node in parse(data):
                if node.tag=="{"+MODERN+"}author":authors[node.get("id")]=node.get("name","")
                elif node.tag=="{"+NS["p"]+"}cmAuthor":legacy[node.get("id")]=node.get("name","")
    rows=[];modern_seen=False
    for sid,part,slide in backend._slide_entries(package)[1]:
        relations=posixpath.join(posixpath.dirname(part),"_rels",posixpath.basename(part)+".rels")
        if relations not in package:continue
        for relation in parse(package[relations][1]):
            if not relation.get("Type","").endswith("/comments"):continue
            if relation.get("TargetMode")=="External":raise StudioError(ErrorCode.SECURITY_BLOCK,"Comment relationship must remain inside the validated snapshot")
            target=posixpath.normpath(posixpath.join(posixpath.dirname(part),relation.get("Target")))
            if target not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Comment part is missing")
            root=parse(package[target][1]);namespace=root.tag.split("}")[0][1:]
            if namespace not in {MODERN,NS["p"]}:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Unrecognized comment schema; no comments were silently omitted")
            modern_seen=modern_seen or namespace==MODERN
            for comment in root:
                if comment.tag!="{"+namespace+"}cm":continue
                author_id=comment.get("authorId")
                position=comment.find("{"+namespace+"}pos")
                row={"slide_id":sid,"author":(authors if namespace==MODERN else legacy).get(author_id,author_id or "Unknown author"),"created_at":comment.get("created") if namespace==MODERN else comment.get("dt"),"text":visible_text(comment,namespace),"anchor":{"left_pt":int(position.get("x"))/12700,"top_pt":int(position.get("y"))/12700} if position is not None else {"left_pt":None,"top_pt":None},"replies":[]}
                identity={"slide_id":sid,"native_id":comment.get("id",comment.get("idx")),"author_id":author_id,"text":row["text"],"created_at":row["created_at"],"anchor":row["anchor"]}
                row["annotation_id"]="ann_"+digest(identity)
                reply_rows=[]
                for reply in comment.findall("{"+MODERN+"}replyLst/{"+MODERN+"}reply"):
                    text=visible_text(reply,MODERN)
                    data={"author":authors.get(reply.get("authorId"),"Unknown author"),"created_at":reply.get("created"),"text":text}
                    row["replies"].append(data)
                    reply_row={**deepcopy(row),**data,"replies":[],"parent_annotation_id":row["annotation_id"]}
                    reply_row["annotation_id"]="ann_"+digest({"parent":row["annotation_id"],"native_id":reply.get("id"),**data})
                    reply_rows.append(reply_row)
                rows.extend([row,*reply_rows])
    return rows,{"comments_read":True,"replies_read":modern_seen,"modern_comments_snapshot":modern_seen,"source":"current_live_snapshot"}
