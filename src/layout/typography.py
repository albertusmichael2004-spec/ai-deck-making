"""Conservative word wrapping using the installed font's actual glyph advances."""
import re
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from state.errors import StudioError,ErrorCode


@lru_cache(maxsize=128)
def installed_font(family,points,bold):
    stems={"Arial":("arial","arialbd"),"Calibri":("calibri","calibrib"),"Aptos":("aptos","aptos-bold"),"Segoe UI":("segoeui","segoeuib")}
    stem=stems.get(family,(family.replace(" ","").lower(),)*2)[int(bool(bold))]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",stem):return None
    path=Path("C:/Windows/Fonts")/(stem+".ttf")
    return ImageFont.truetype(str(path),round(points*2)) if path.is_file() else None


def wrap_text(text,width_in,family,points,bold=False):
    font=installed_font(family,points,bold);limit=width_in*72*2
    def length(value):return font.getlength(value) if font else len(value)*points*1.24
    lines=[]
    for paragraph in text.split("\n"):
        current=""
        for word in paragraph.split():
            if length(word)>limit:raise StudioError(ErrorCode.QA_FAILURE,"A text token exceeds the readable column; rewrite or split the content")
            candidate=(current+" "+word).strip()
            if current and length(candidate)>limit*.95:lines.append(current);current=word
            else:current=candidate
        lines.append(current)
    return "\n".join(lines)
