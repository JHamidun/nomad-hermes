"""Tests for the pre_kanban_task_create pre-commit veto hook."""

from __future__ import annotations

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import plugins


@pytest.fixture
def isolated_kanban(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(tmp_path))
    kb.init_db()
    return tmp_path


def test_pre_kanban_task_create_in_valid_hooks():
    assert "pre_kanban_task_create" in plugins.VALID_HOOKS


def test_pre_kanban_task_create_veto_prevents_insert(isolated_kanban, monkeypatch):
    seen_payloads: list[dict] = []

    def fake_has_hook(event: str) -> bool:
        return event == "pre_kanban_task_create"

    def fake_invoke_hook(event: str, **kwargs):
        if event == "pre_kanban_task_create":
            seen_payloads.append(kwargs)
            return [{"action": "veto", "reason": "disallowed model override"}]
        return []

    monkeypatch.setattr("hermes_cli.lifecycle.has_hook", fake_has_hook)
    monkeypatch.setattr("hermes_cli.lifecycle.invoke_hook", fake_invoke_hook)

    with kbc.connect_closing() as conn:
        with pytest.raises(kb.KanbanTaskCreateVetoed, match="disallowed model override"):
            kb.create_task(
                conn,
                title="Blocked card",
                assignee="dev",
                model_override="restricted-model",
            )
        rows = conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        assert rows["n"] == 0
        events = conn.execute("SELECT COUNT(*) AS n FROM task_events").fetchone()
        assert events["n"] == 0

    assert len(seen_payloads) == 1
    assert seen_payloads[0]["title"] == "Blocked card"
    assert seen_payloads[0]["assignee"] == "dev"
    assert seen_payloads[0]["model_override"] == "restricted-model"


def test_pre_kanban_task_create_allow_inserts_row(isolated_kanban, monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.lifecycle.has_hook",
        lambda event: event == "pre_kanban_task_create",
    )
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda event, **kwargs: [{"action": "allow"}],
    )

    with kbc.connect_closing() as conn:
        tid = kb.create_task(conn, title="Allowed card", assignee="dev")
        task = kb.get_task(conn, tid)
        assert task is not None
        assert task.title == "Allowed card"
