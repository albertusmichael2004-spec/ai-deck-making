"""Pure decoding shared by transport and independent provenance verification."""
import hashlib
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit

from research.quality import canonical_url
from state.errors import StudioError,ErrorCode


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__();self.text=[];self.links=[];self.skip=0;self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","noscript"}:self.skip+=1
        if tag=="title":self.in_title=True
        if tag=="a" and not self.skip:
            href=dict(attrs).get("href")
            if href:self.links.append(href)
        if tag in {"p","br","div","li","h1","h2","h3","tr"}:self.text.append("\n")
    def handle_endtag(self,tag):
        if tag in {"script","style","noscript"}:self.skip=max(0,self.skip-1)
        if tag=="title":self.in_title=False
    def handle_data(self,data):
        if not self.skip:self.text.append(data)
        if self.in_title:self.title.append(data)


def decode_document(data,mime,url):
    title="";links=[]
    if mime=="application/pdf" or data.startswith(b"%PDF-"):
        import pymupdf
        with pymupdf.open(stream=data,filetype="pdf") as doc:
            if doc.needs_pass:raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Research PDF requires authorized decryption")
            regions=[{"locator":f"page:{i+1}","text":page.get_text()} for i,page in enumerate(doc)]
        text="\n".join(row["text"] for row in regions)
    elif mime in {"text/html","application/xhtml+xml"}:
        parser=HTMLText();parser.feed(data.decode("utf-8",errors="replace"));text="".join(parser.text);title="".join(parser.title).strip()
        for href in parser.links:
            joined=urljoin(url,href)
            if urlsplit(joined).scheme not in {"http","https"}:continue
            try:links.append(canonical_url(joined))
            except StudioError:continue
        regions=[{"locator":"document:text","text":text}]
    elif mime in {"text/plain","application/json"}:
        text=data.decode("utf-8");regions=[{"locator":"document:text","text":text}]
    else:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Unsupported research document MIME",mime=mime)
    return {"text":text,"regions":regions,"title":title,"links":list(dict.fromkeys(links)),"sha256":hashlib.sha256(data).hexdigest(),"text_sha256":hashlib.sha256(text.encode()).hexdigest()}
