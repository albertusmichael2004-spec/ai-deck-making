from copy import deepcopy

from ir.identity import object_id
from layout.brand import BrandRegistry
from state.errors import StudioError,ErrorCode
from textwrap import wrap
from layout.typography import wrap_text


DIAGRAMS={"timeline","roadmap","issue_tree","scenario","recommendation","text","shapes"}


class ConsultingLayout:
    def __init__(self,repository):self.brands=BrandRegistry(repository)
    def compile(self,deck,slide,source_notes=()):
        brand=self.brands.get(slide["brand_profile"]);grid=brand["grid"];fonts=brand["fonts"];colors=brand["colors"]
        width,height=deck["canvas"]["width_in"],deck["canvas"]["height_in"]
        margin=grid["margin_in"];usable=width-2*margin;source_y=height-grid["source_y_from_bottom_in"]
        content_y=grid["content_y_in"];content_h=source_y-content_y-.25
        if content_h<2 or usable<5:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Canvas cannot accommodate the consulting grid")
        density=brand["density"]
        if len(slide["action_title"])>density["maximum_title_characters"] or len(slide["key_message"])>density["maximum_message_characters"]:raise StudioError(ErrorCode.QA_FAILURE,"Message density requires rewriting or splitting, not unreadable fonts")
        objects=[];role_counts={}
        def obj(role,kind,x,y,w,h,**values):
            slot=role_counts.get(role,0);role_counts[role]=slot+1
            item={"schema_version":"1.1","object_id":object_id(deck["deck_id"],slide["slide_id"],role+str(slot)),"kind":kind,"role":role if role in {"title","body","source","label","decoration","exhibit","annotation"} else "label","x":x,"y":y,"width":w,"height":h,"protection":"MUST_NOT_CHANGE" if role in {"source","exhibit"} else "MAY_CHANGE",**values}
            if kind=="text":item={"font_pt":fonts["label_pt"],"font_family":fonts["family"],"color":colors["foreground"],**item}
            if kind=="text":
                item["text"]=wrap_text(item.get("text",""),w,item["font_family"],item["font_pt"],item.get("bold",False))
                if role=="title" and len(item["text"].splitlines())>2:raise StudioError(ErrorCode.QA_FAILURE,"Action title exceeds two measured readable lines")
            objects.append(item);return item
        title_lines=wrap(slide["action_title"],width=density.get("maximum_title_line_characters",60),break_long_words=False,break_on_hyphens=False)
        if len(title_lines)==2 and min(map(len,title_lines))<len(slide["action_title"])*.25:
            words=slide["action_title"].split();candidates=[(" ".join(words[:index])," ".join(words[index:])) for index in range(1,len(words))]
            candidates=[pair for pair in candidates if max(map(len,pair))<=density.get("maximum_title_line_characters",60)]
            if candidates:title_lines=min(candidates,key=lambda pair:abs(len(pair[0])-len(pair[1])))
        if len(title_lines)>2:raise StudioError(ErrorCode.QA_FAILURE,"Action title requires rewriting to fit two readable lines")
        obj("title","text",margin,grid["title_y_in"],usable,grid["title_height_in"],text="\n".join(title_lines),font_pt=fonts["title_pt"],bold=True)
        obj("decoration","shape",margin,grid["title_y_in"]+grid["title_height_in"]+.1,usable,.025,fill=colors["accent"])
        obj("body","text",margin,grid["message_y_in"],usable,.6,text=slide["key_message"],font_pt=fonts["body_pt"])
        exhibit=slide["exhibit"];kind=exhibit["type"];insights=slide.get("insights",[])
        archetype=slide["layout"]["archetype"]
        if archetype not in {"consulting","single_exhibit","two_column","executive_summary","comparison","roadmap","baseline"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown consulting archetype")
        panel_w=(usable-grid["gutter_in"])*.7 if archetype=="two_column" and insights else usable
        footer_texts=[]
        if archetype!="two_column" and insights and ("resolved_series" in exhibit or "resolved_rows" in exhibit):footer_texts.append(" • ".join(insights))
        for annotation in slide.get("annotations",[]):
            if annotation["target"] not in {"exhibit","message"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Annotation target is not a compiled exhibit/message")
            footer_texts.append(annotation["intent"])
        if len(footer_texts)>3 or any(len(text)>220 for text in footer_texts):raise StudioError(ErrorCode.QA_FAILURE,"Annotation density exceeds a readable reserved strip")
        content_h-=.55*len(footer_texts)
        if "resolved_series" in exhibit:
            if len(exhibit["resolved_categories"])>density["maximum_categories"]:raise StudioError(ErrorCode.QA_FAILURE,"Too many categories for a readable core exhibit")
            obj("exhibit","chart",margin,content_y,panel_w,content_h,chart={"type":kind,"categories":exhibit["resolved_categories"],"series":exhibit["resolved_series"],"colors":colors,"font_family":fonts["family"],"font_pt":fonts["label_pt"],"unit":exhibit.get("unit",""),"number_format":exhibit.get("number_format","General")})
        elif "resolved_rows" in exhibit:
            rows=exhibit["resolved_rows"];headers=exhibit["headers"]
            if len(rows)>density["maximum_table_rows"] or len(headers)>density["maximum_table_columns"]:raise StudioError(ErrorCode.QA_FAILURE,"Table density exceeds the readable grid")
            obj("exhibit","table",margin,content_y,panel_w,min(content_h,(len(rows)+1)*.5),table={"headers":headers,"rows":rows,"colors":colors,"font_family":fonts["family"],"font_pt":fonts["label_pt"]})
        elif kind in DIAGRAMS:
            items=exhibit.get("items",[])
            if not items:items=[{"title":text,"body":""} for text in insights] or [{"title":slide["key_message"],"body":""}]
            if len(items)>density["maximum_diagram_items"]:raise StudioError(ErrorCode.QA_FAILURE,"Diagram requires a split or appendix")
            columns=min(len(items),3 if kind in {"scenario","recommendation","issue_tree","text","shapes"} else 4)
            rows=(len(items)+columns-1)//columns;cell_w=(panel_w-(columns-1)*grid["gutter_in"])/columns;cell_h=(content_h-(rows-1)*grid["gutter_in"])/rows
            positions=None
            if kind=="issue_tree" and all("id" in item for item in items):
                from layout.tree import tree_positions
                positions=tree_positions(items,margin,content_y,panel_w,content_h,grid["gutter_in"])
            for index,item in enumerate(items):
                x=margin+(index%columns)*(cell_w+grid["gutter_in"]);y=content_y+(index//columns)*(cell_h+grid["gutter_in"])
                if positions:
                    position=positions[item["id"]];x,y,cell_w,cell_h=(position[key] for key in ["x","y","width","height"])
                if kind in {"roadmap","timeline"}:
                    obj("decoration","shape",x,y,cell_w,.12,fill=colors["accent"],geometry="chevron")
                    y+=.25;cell_content_h=cell_h-.25
                else:cell_content_h=cell_h
                obj("label","text",x,y,cell_w,.7,text=item["title"],font_pt=fonts["body_pt"],bold=True,color=colors["accent"])
                if item.get("body"):obj("body","text",x,y+.85,cell_w,max(.4,cell_content_h-.85),text=item["body"],font_pt=fonts["label_pt"])
            if positions:
                for item in items:
                    if item.get("parent_id") is None:continue
                    parent,child=positions[item["parent_id"]],positions[item["id"]]
                    start=parent["x"]+parent["width"]/2;end=child["x"]+child["width"]/2
                    obj("decoration","shape",min(start,end),parent["y"]+parent["height"]+.04,max(.02,abs(end-start)),max(.02,child["y"]-parent["y"]-parent["height"]-.08),geometry="line",flip_h=end<start,color=colors["accent"])
        else:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Exhibit has no source-bound renderer",exhibit=kind)
        if archetype=="two_column" and insights:
            x=margin+panel_w+grid["gutter_in"];obj("body","text",x,content_y,usable-panel_w-grid["gutter_in"],content_h,text="\n\n".join(insights),font_pt=fonts["body_pt"])
        for index,text in enumerate(footer_texts):obj("annotation","text",margin,content_y+content_h+.12+index*.55,panel_w,.4,text=text,font_pt=fonts["label_pt"],bold=True,color=colors["accent"])
        if source_notes:obj("source","text",margin,source_y,usable,.4,text="; ".join(source_notes),font_pt=fonts["source_pt"])
        return {"slide_id":slide["slide_id"],"objects":objects,"background":colors["background"],"brand_warnings":brand["warnings"]}
