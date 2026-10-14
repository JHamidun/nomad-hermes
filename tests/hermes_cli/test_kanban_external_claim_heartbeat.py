"""Tests for external Kanban claim renewal without worker_pid via heartbeat."""

from __future__ import annotations

import pytest

from hermes_cli import kanban
from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc


@pytest.fixture
def isolated_kanban(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(tmp_path))
    kb.init_db()
    return tmp_path


def test_host_prefix_is_public():
    prefix = kb.host_prefix()
    assert isinstance(prefix, str)
    assert prefix.endswith(":")
    assert prefix == kb._host_prefix()


def test_external_claim_without_worker_pid_survives_past_ttl_via_heartbeat(isolated_kanban, monkeypatch):
    base_now = 1_700_000_000
    current_time = [base_now]
    monkeypatch.setattr("hermes_cli.kanban_db.time.time", lambda: current_time[0])
    monkeypatch.setattr("hermes_cli.kanban_db_dispatch.time.time", lambda: current_time[0])

    with kbc.connect_closing() as conn:
        tid = kb.create_task(conn, title="External lane task", assignee="external-lane")
        claimed = kb.claim_task(
            conn,
            tid,
            ttl_seconds=60,
            claimer=f"{kb.host_prefix()}999999",
        )
        assert claimed is not None
        assert claimed.worker_pid is None

        # Advance 45s and renew via heartbeat_claim (simulating a different CLI PID on the same host)
        current_time[0] = base_now + 45
        assert kb.heartbeat_claim(conn, tid, ttl_seconds=60, note="still working") is True

        # Advance to base_now + 80 (past initial 60s TTL, within renewed 105s TTL)
        current_time[0] = base_now + 80
        assert kb.release_stale_claims(conn) == 0
        task = kb.get_task(conn, tid)
        assert task is not None
        assert task.status == "running"
        assert task.last_heartbeat_at == base_now + 45
        assert task.claim_expires == base_now + 105

        # Renew again via CLI `kanban heartbeat` at base_now + 95
        current_time[0] = base_now + 95
        out = kanban.run_slash(f"heartbeat {tid} --ttl 60 --note step-2")
        assert "Heartbeat recorded" in out

        # Advance to base_now + 140 (more than 2x initial TTL); still running, not reclaimed or re-spawned
        current_time[0] = base_now + 140
        assert kb.release_stale_claims(conn) == 0
        task_after = kb.get_task(conn, tid)
        assert task_after is not None
        assert task_after.status == "running"
        assert task_after.worker_pid is None
        assert task_after.last_heartbeat_at == base_now + 95
        assert task_after.claim_expires == base_now + 155
        runs = kb.list_runs(conn, tid)
        assert len(runs) == 1
        assert runs[0].status == "running"
        assert runs[0].last_heartbeat_at == base_now + 95
        assert runs[0].claim_expires == base_now + 155
