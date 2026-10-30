import re

from PIL import Image


def describe(slide,native,source,preview):
    objects=slide["objects"];text="\n".join(obj["text"] for obj in objects if obj["text"])
    title=next((obj["text"] for obj in objects if obj["role"]=="title"),text.split("\n")[0] if text else "Untitled reference")
    charts=[obj for obj in objects if obj.get("content_type")=="chart"];tables=[obj for obj in objects if obj.get("content_type")=="table"]
    geometry=[obj["geometry"] for obj in objects if obj["geometry"]]
    x_positions=sorted({round(obj["x"],1) for obj in geometry if obj["width"]>1})
    # These are observed descriptors, not model-invented business facts.
    fonts=sorted({run["font_name"] for shape in native["shapes"] for run in shape.get("runs",[])})
    chart_types=sorted({row.get("chart_type") for shape in native["shapes"] for row in shape.get("chart_series",[]) if row.get("chart_type") is not None})
    with Image.open(preview) as image:
        thumbnail=image.convert("RGB").resize((64,36));data=thumbnail.tobytes();pixels=[data[offset:offset+3] for offset in range(0,len(data),3)]
        mean=[round(sum(pixel[channel] for pixel in pixels)/len(pixels),2) for channel in range(3)]
        nonwhite=sum(min(pixel)<235 for pixel in pixels)/len(pixels)
    kind="chart" if charts else "table" if tables else "diagram" if any(obj["kind"] in {"cxnSp","grpSp"} for obj in objects) else "text"
    return {"semantic":{"title":title,"text":text,"tokens":sorted(set(re.findall(r"[\w]+",text.lower()))),"purpose":kind,"industry":source.get("industry","unknown"),"audience":source.get("audience","unknown"),"classification_method":"deterministic_observed_content"},"visual":{"fonts":fonts,"declared_palette":source.get("declared_palette",[]),"theme_hashes":source.get("theme_hashes",{}),"mean_rgb":mean,"nonwhite_fraction":round(nonwhite,4),"aspect_ratio":source["canvas"]["width_in"]/source["canvas"]["height_in"]},"structural":{"content_shape":kind,"object_count":len(objects),"chart_count":len(charts),"table_count":len(tables),"chart_types":chart_types,"text_characters":len(text),"columns_observed":len(x_positions),"elements":[{"object_id":obj["object_id"],"native_id":obj["native_id"],"kind":obj["kind"],"role":obj["role"],"geometry":obj["geometry"],"fingerprint":obj["fingerprint"]} for obj in objects]},"brand":source.get("brand","unknown")}
