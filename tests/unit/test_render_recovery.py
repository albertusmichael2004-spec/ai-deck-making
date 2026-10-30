from pathlib import Path
from types import SimpleNamespace
import pytest
from presentation.rendering.recovery import recover_render_copy
from state.errors import StudioError
from state.io import sha256


@pytest.mark.parametrize('saved,readonly',[(True,True),(False,True),(True,False)])
def test_recovery_only_closes_saved_readonly_exact_worker_copy(tmp_path,saved,readonly):
    source=tmp_path/'runtime/native_render'/('a'*32)/'input.pptx'
    source.parent.mkdir(parents=True);source.write_bytes(b'render')
    closed=[]
    user=SimpleNamespace(FullName=str(tmp_path/'user.pptx'),Saved=True,ReadOnly=True,Close=lambda:closed.append('user'))
    owned=SimpleNamespace(FullName=str(source),Saved=saved,ReadOnly=readonly,Close=lambda:closed.append('render'))
    app=SimpleNamespace(Presentations=SimpleNamespace(Count=2,Item=lambda index:[user,owned][index-1]))
    result=recover_render_copy(tmp_path,source,sha256(source),app)
    assert closed==(['render'] if saved and readonly else [])
    assert result['status']==('closed_renderer_copy' if saved and readonly else 'refused')


def test_recovery_rejects_unowned_path_and_changed_copy(tmp_path):
    user=tmp_path/'input.pptx';user.write_bytes(b'user')
    with pytest.raises(StudioError):recover_render_copy(tmp_path,user,sha256(user),object())
    source=tmp_path/'runtime/native_render'/('b'*32)/'input.pptx'
    source.parent.mkdir(parents=True);source.write_bytes(b'changed')
    with pytest.raises(StudioError):recover_render_copy(tmp_path,source,'0'*64,object())
