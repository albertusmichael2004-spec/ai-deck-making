import re

from state.errors import StudioError,ErrorCode


TYPES={"DESIGN_FEEDBACK","FACTUAL_CORRECTION","NEW_REQUIREMENT","DATA_UPDATE","BRAND_CHANGE","COPY_PREFERENCE","SCOPE_CHANGE","OTHER"}
POLARITIES={"positive","negative","neutral","deprecated"}
POSITIVE_SIGNALS={"accepted_without_redesign","selected_from_alternatives","reused_pattern"}
NEGATIVE_SIGNALS={"immediate_redesign","pattern_removed","major_restructure"}


def classify(text,*,declared_type=None,polarity=None,signal=None):
    value=text.lower()
    if declared_type is not None and declared_type not in TYPES or polarity is not None and polarity not in POLARITIES:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown feedback classification")
    if signal is not None and signal not in POSITIVE_SIGNALS|NEGATIVE_SIGNALS:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown implicit feedback signal")
    typography=bool(re.search(r"\b(font|typeface|spacing|pt|point size|ukuran huruf|jarak|bold|tebal|italic)\b",value))
    factual=bool(re.search(r"\b(wrong number|incorrect|factual|fact correction|angka salah|salah angka|koreksi angka|data salah)\b",value) or not typography and re.search(r"\b(change|replace|correct|ubah|ganti|koreksi)\b.*\d.*\b(to|with|menjadi|ke)\b.*\d",value))
    if factual:kind="FACTUAL_CORRECTION"
    elif declared_type:kind=declared_type
    elif re.search(r"\b(new data|refresh data|updated data|data baru|csv|spreadsheet)\b",value):kind="DATA_UPDATE"
    elif re.search(r"\b(new requirement|add a slide|include a section|tambah slide|tambahkan)\b",value):kind="NEW_REQUIREMENT"
    elif re.search(r"\b(brand|branding|logo|corporate color|warna perusahaan)\b",value):kind="BRAND_CHANGE"
    elif re.search(r"\b(scope|only this|selected object|hanya slide|hanya objek)\b",value):kind="SCOPE_CHANGE"
    elif re.search(r"\b(wording|tone|concise|copy|bahasa|kalimat|ringkas)\b",value):kind="COPY_PREFERENCE"
    elif signal or typography or re.search(r"\b(layout|design|crowded|redesign|card|balance|density|too ai.generated|desain|padat|tata letak)\b",value):kind="DESIGN_FEEDBACK"
    else:kind="OTHER"
    if kind not in {"DESIGN_FEEDBACK","COPY_PREFERENCE"}:effective="neutral"
    elif polarity:effective=polarity
    elif signal:effective="positive" if signal in POSITIVE_SIGNALS else "negative"
    elif re.search(r"\b(deprecate|never use|stop using|jangan gunakan lagi)\b",value):effective="deprecated"
    elif re.search(r"\b(reject|too|dislike|bad|crowded|remove|redesign|tolak|terlalu|tidak suka|padat)\b",value):effective="negative"
    elif re.search(r"\b(approve|accept|like|clear|good|save.*reference|setuju|bagus|suka|jelas)\b",value):effective="positive"
    else:effective="neutral"
    return {"type":kind,"polarity":effective,"learnable":kind in {"DESIGN_FEEDBACK","COPY_PREFERENCE"} and effective!="neutral","implicit":signal is not None,"signal":signal}
