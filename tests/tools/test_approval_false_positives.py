"""Regression tests for dangerous-command false positives (docker -h, quoted prose)."""

from __future__ import annotations

import pytest

from tools.approval_detection import detect_dangerous_command


@pytest.mark.parametrize(
    "cmd",
    [
        "docker -h",
        "docker -h ps",
        "docker --help",
        "docker --version",
        'echo "see docker -H ssh://prod for remote daemon"',
        'git commit -m "fix del /s parser and docker -H handling"',
        "git commit -m 'document rd /s /q cleanup'",
    ],
)
def test_benign_help_and_quoted_prose_do_not_trigger(cmd: str):
    is_dangerous, key, desc = detect_dangerous_command(cmd)
    assert not is_dangerous, f"Expected benign command {cmd!r} to pass, got {key!r} ({desc!r})"


@pytest.mark.parametrize(
    "cmd",
    [
        "docker -H ssh://prod ps",
        "docker --host=tcp://10.0.0.1:2375 stop web",
        "docker -c prod-context ps",
        "del /s /q C:\\temp\\cache",
        "del C:\\data /s /q",
        "rmdir /s /q build",
    ],
)
def test_real_redirects_and_deletes_still_trigger(cmd: str):
    is_dangerous, key, _ = detect_dangerous_command(cmd)
    assert is_dangerous, f"Expected dangerous command {cmd!r} to be flagged"
    assert key is not None
