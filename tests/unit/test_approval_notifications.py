import json
from pathlib import Path
from types import SimpleNamespace
from cli.codex_launcher import command
from presentation.live.session import LiveSession
from state.errors import StudioError
import pytest


def test_approval_notifications_keep_sandbox_and_approval_policy(repo,project):
    args=command(repo,project,repo/"codex.exe")
    assert args[args.index("-a")+1]=="on-request"
    assert args[args.index("-s")+1]=="workspace-write"
    assert 'tui.notifications=["approval-requested","agent-turn-complete"]' in args
    assert 'tui.notification_condition="always"' in args
    assert 'tui.notification_method="bel"' in args
    settings=json.loads((Path(__file__).resolve().parents[2]/".vscode/settings.json").read_text())
    assert settings["terminal.integrated.enableVisualBell"] is True
    assert settings["accessibility.signals.terminalBell"]["sound"]=="on"


def test_live_style_preflight_requires_file_mode_before_accessing_com(repo,project):
    session=LiveSession(repo,project,SimpleNamespace())
    patch={"schema_version":"1.2","patch_id":"preflight","operations":[{"slide_id":"s","object_id":"o","expected_fingerprint":"0"*64,"operation":"set_gradient_fill","value":{"angle_deg":0,"stops":[{"position":0,"color":"FFFFFF"},{"position":1,"color":"000000"}]}}]}
    scope={"objects":[{"slide_id":"s","object_id":"o","protection":"MAY_CHANGE"}]}
    with pytest.raises(StudioError,match="file revision") as error:session.apply(patch,scope,{},None)
    assert error.value.details["permission_exception_required"] is False
