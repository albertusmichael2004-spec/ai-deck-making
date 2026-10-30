"""Close only an identified, saved, read-only renderer copy after worker exit."""
import re
from pathlib import Path
from state.io import native_path, logical_path, sha256
from state.errors import StudioError, ErrorCode


def recover_render_copy(repository,source,expected_hash,application=None):
    base=native_path(Path(repository)/'runtime/native_render')
    source=native_path(source)
    if not source.is_relative_to(base) or source.name!='input.pptx' or source.parent.parent!=base or not re.fullmatch('[a-f0-9]{32}',source.parent.name):
        raise StudioError(ErrorCode.SECURITY_BLOCK,'Recovery only accepts a renderer-owned staging copy')
    if sha256(source)!=expected_hash:
        raise StudioError(ErrorCode.SOURCE_CONFLICT,'Render recovery copy changed')
    if application is None:
        import win32com.client
        application=win32com.client.GetActiveObject('PowerPoint.Application')
    for index in range(1,int(application.Presentations.Count)+1):
        deck=application.Presentations.Item(index)
        if native_path(Path(str(deck.FullName)))!=source:continue
        if not bool(deck.ReadOnly) or not bool(deck.Saved):
            return {'status':'refused','reason':'render_copy_is_editable_or_modified'}
        deck.Close()
        return {'status':'closed_renderer_copy','path':str(logical_path(source))}
    return {'status':'no_matching_renderer_copy'}
