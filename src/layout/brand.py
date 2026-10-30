import re
from pathlib import Path

from state.io import read_yaml,native_path
from state.errors import StudioError,ErrorCode
from ir.validation import validate


class BrandRegistry:
    def __init__(self,repository):self.repository,self.path=repository,repository/"config/brands"
    def get(self,identifier):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+",identifier):raise StudioError(ErrorCode.SECURITY_BLOCK,"Invalid brand identifier")
        path=self.path/(identifier+".yaml")
        if not path.is_file():raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Brand profile is not registered")
        tokens=read_yaml(path)
        validate(self.repository,"brand_profile",tokens)
        if tokens["brand_id"]!=identifier:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Brand identity differs from its registered profile")
        grid=tokens["grid"];sizes=tokens["fonts"]
        if not sizes["title_pt"]>=sizes["body_pt"]>=sizes["label_pt"]>=sizes["source_pt"] or not grid["title_y_in"]+grid["title_height_in"]+.125<=grid["message_y_in"] or grid["message_y_in"]+.6>grid["content_y_in"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Brand hierarchy or reserved text grid is inconsistent")
        for value in tokens["colors"].values():
            if not isinstance(value,str) or not re.fullmatch(r"[a-fA-F0-9]{6}",value):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid brand color")
        if any(not isinstance(value,(int,float)) or value<12 for key,value in tokens["fonts"].items() if key.endswith("_pt")):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Brand typography violates minimum readable size")
        fonts=native_path(Path("C:/Windows/Fonts"))
        available={path.stem.lower() for path in fonts.iterdir()} if fonts.exists() else set()
        family=tokens["fonts"]["family"]
        aliases={"Arial":"arial","Calibri":"calibri","Aptos":"aptos","Segoe UI":"segoeui"}
        wanted=aliases.get(family,family.replace(" ","").lower())
        warnings=[]
        if available and not any(wanted in name for name in available):
            fallback=tokens["fonts"]["fallback"];wanted=aliases.get(fallback,fallback.lower())
            if not any(wanted in name for name in available):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Brand and fallback fonts are unavailable")
            tokens["fonts"]["family"]=fallback;warnings.append({"code":"FONT_FALLBACK","requested":family,"selected":fallback})
        tokens["warnings"]=warnings
        return tokens
