from copy import deepcopy
from pathlib import Path

from lxml import etree as ET

from layout.adaptive import AdaptiveLayoutCompiler
from presentation.backends.ooxml import OOXMLBackend
from presentation.backends.xml import NS,parse,serialize,element
from presentation.compiler.compiler import PresentationCompiler
from presentation.live.annotations import CommentLedger
from presentation.live.file_comments import read_comments,MODERN
from state.io import read_json


def test_modern_unsaved_snapshot_replies_keep_parent_id_and_process_new_reply(repo,project):
    backend=OOXMLBackend(repo);spec=read_json(Path(__file__).parents[1]/"fixtures/basic_spec.json");source=project.path/"work/comment_snapshot.pptx"
    PresentationCompiler(repo,AdaptiveLayoutCompiler(repo),backend).compile(**spec,destination=source)
    package=backend._read(source);slide_part=backend.inspect(source)["slides"][0]["part"]
    rel_name="ppt/slides/_rels/"+Path(slide_part).name+".rels";rels=parse(package[rel_name][1])
    rels.append(element("rel","Relationship",Id="comment",Type="http://schemas.microsoft.com/office/2018/10/relationships/comments",Target="../comments/modern.xml"));package[rel_name]=(package[rel_name][0],serialize(rels))
    author=ET.Element("{"+MODERN+"}authorLst");ET.SubElement(author,"{"+MODERN+"}author",id="reviewer",name="Fixture Reviewer",userId="fixture",providerId="fixture")
    package["ppt/authors.xml"]=(None,serialize(author))
    comments=ET.Element("{"+MODERN+"}cmLst");comment=ET.SubElement(comments,"{"+MODERN+"}cm",id="controlled_comment",authorId="reviewer",created="2026-10-12T01:00:00Z");ET.SubElement(comment,"{"+MODERN+"}pos",x=str(40*12700),y=str(30*12700))
    def body(node,text):
        tx=ET.SubElement(node,"{"+MODERN+"}txBody");paragraph=ET.SubElement(tx,"{"+NS['a']+"}p");run=ET.SubElement(paragraph,"{"+NS['a']+"}r");ET.SubElement(run,"{"+NS['a']+"}t").text=text
    body(comment,"Make the title concise")
    package["ppt/comments/modern.xml"]=(None,serialize(comments));backend._write(package,source)
    rows,caps=read_comments(backend,source);assert caps["modern_comments_snapshot"] and rows[0]["author"]=="Fixture Reviewer" and rows[0]["anchor"]=={"left_pt":40,"top_pt":30}
    ledger=CommentLedger(project);ledger.scan(rows);ledger.mark(rows[0]["annotation_id"],"applied",transaction_id="prior")
    replies=ET.SubElement(comment,"{"+MODERN+"}replyLst");reply=ET.SubElement(replies,"{"+MODERN+"}reply",id="new_reply",authorId="reviewer",created="2026-10-12T02:00:00Z");body(reply,"Keep the chart numbers intact")
    package["ppt/comments/modern.xml"]=(None,serialize(comments));backend._write(package,source)
    updated,caps=read_comments(backend,source)
    assert updated[0]["annotation_id"]==rows[0]["annotation_id"] and len(updated)==2 and updated[1]["parent_annotation_id"]==rows[0]["annotation_id"]
    new=ledger.scan(updated);assert len(new)==1 and new[0]["comment"]["text"]=="Keep the chart numbers intact"
