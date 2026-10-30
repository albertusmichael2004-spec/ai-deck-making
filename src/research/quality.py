from datetime import datetime,timezone
from urllib.parse import urlsplit,parse_qsl,urlunsplit,urlencode
import hashlib
import re

from state.errors import StudioError,ErrorCode


PRIMARY_TYPES={"official_statistics","regulator","company_filing","official_disclosure","standards_body","original_research","official_documentation"}
SCORES={**{name:.95 for name in PRIMARY_TYPES},"independent_news":.8,"research_institution":.8,"trade_publication":.7,"general_web":.4,"community":.3}


def canonical_url(url):
    parsed=urlsplit(url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:
        raise StudioError(ErrorCode.SECURITY_BLOCK,"Research requires an ordinary public HTTP(S) URL")
    query=[(key,value) for key,value in parse_qsl(parsed.query,keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in {"gclid","fbclid"}]
    return urlunsplit((parsed.scheme,parsed.netloc.lower(),parsed.path or "/",urlencode(sorted(query)),""))


def source_quality(source,question,now=None):
    now=now or datetime.now(timezone.utc)
    authority=SCORES.get(source.get("source_type"),.3)
    fit=source.get("question_fit",0)
    if not isinstance(fit,(int,float)) or not 0<=fit<=1:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid source question-fit score")
    fresh=True
    if question.get("period") and source.get("period")!=question["period"]:fresh=False
    if question.get("max_age_days") is not None:
        try:
            date=datetime.fromisoformat(source.get("published_at"))
            if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
            fresh=fresh and 0<=(now-date).days<=question["max_age_days"]
        except (TypeError,ValueError):fresh=False
    if question.get("geography") and source.get("geography")!=question["geography"]:fit=min(fit,.5)
    if question.get("definition") and source.get("definition")!=question["definition"]:fit=min(fit,.5)
    primary=source.get("source_type") in PRIMARY_TYPES
    return {"authority":authority,"question_fit":fit,"freshness_status":"current_or_period_correct" if fresh else "stale_or_unknown","eligible":authority>=.7 and fit>=.75 and fresh,"definitive_primary":primary and source.get("definitive") is True}


def content_fingerprint(text):
    normalized=re.sub(r"\s+"," ",text).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def validate_finding(finding,document):
    quote=re.sub(r"\s+"," ",finding["quote"]).strip()
    text=re.sub(r"\s+"," ",document["text"])
    region=next((row for row in document["regions"] if row["locator"]==finding.get("locator")),None)
    if not quote or quote not in text or not region or quote not in re.sub(r"\s+"," ",region["text"]):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Finding lacks an inspected exact quote and locator")
    if len(quote.split())>25:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Evidence quote exceeds per-source excerpt budget")
    if finding.get("answer_type")=="numeric":
        value=str(finding.get("value"))
        if not re.search(r"(?<![\d.,])"+re.escape(value)+r"(?![\d.,])",quote):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Numeric finding does not match a complete quoted source value")
        unit=finding.get("unit")
        if not unit or unit.lower() not in quote.lower():
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Numeric finding requires an explicit quoted unit")
