from pathlib import Path
from presentation.rendering.native import NativeRenderer
from types import SimpleNamespace
import subprocess
import pytest
from state.errors import StudioError
from state.io import write_json


def test_timeout_scales_with_selected_slides_and_is_bounded():
    renderer=NativeRenderer(Path('.'))
    assert renderer.worker_timeout(1)==120
    assert renderer.worker_timeout(23)==780
    assert renderer.worker_timeout(10000)==1800


def test_explicit_timeout_is_preserved():
    assert NativeRenderer(Path('.'),timeout_seconds=5).worker_timeout(23)==5


def test_timeout_records_last_stage_without_publishing_partial_output(tmp_path,monkeypatch):
    import presentation.backends.ooxml as backend_module
    import presentation.rendering.native as native
    source=tmp_path/'source.pptx';source.write_bytes(b'original')
    output=tmp_path/'published'
    fake=SimpleNamespace(validate=lambda path:{'passed':True},inspect=lambda path:{'slides':[{},{}]},policy=SimpleNamespace(check=lambda path,**kwargs:path))
    monkeypatch.setattr(backend_module,'OOXMLBackend',lambda root:fake)
    def timeout(command,**options):
        if '--sha256' in command:return SimpleNamespace(returncode=0)
        assert options['timeout']==150
        path=Path(command[command.index('--progress')+1])
        write_json(path,{'stage':'shape_metrics','slide':1,'shape_id':42})
        raise subprocess.TimeoutExpired(command,options['timeout'])
    monkeypatch.setattr(native.subprocess,'run',timeout)
    with pytest.raises(StudioError) as error:NativeRenderer(tmp_path).render(source,output)
    assert error.value.details['progress']['shape_id']==42
    assert error.value.details['timeout_seconds']==150
    assert not output.exists()
    assert source.read_bytes()==b'original'
