import re


def rank(rows,query,weights):
    tokens=set(re.findall(r"[\w]+",query.get("text","").lower()));results=[]
    for row in rows:
        metadata=row["summary"];words=set(metadata["tokens"])
        semantic=len(tokens&words)/max(1,len(tokens))
        shape=float(bool(query.get("content_shape")) and query["content_shape"]==metadata["content_shape"])
        visual=1-abs(query["density"]-metadata["density"]) if "density" in query else 0
        brand=float(bool(query.get("brand")) and query["brand"]==metadata["brand"])
        approved=1 if row["approval"]=="approved" else -1 if row["approval"] in {"rejected","deprecated"} else 0
        scores={"semantic":semantic,"content_shape":shape,"visual":max(0,visual),"brand":brand,"approval":approved}
        total=sum(weights[key]*value for key,value in scores.items())
        results.append({"reference_id":row["reference_id"],"slide_id":row["slide_id"],"library":row["library"],"approval":row["approval"],"score":round(total,6),"components":scores,"summary":metadata,"trust":"untrusted_reference_data"})
    return sorted(results,key=lambda row:(-row["score"],row["reference_id"],row["slide_id"]))
