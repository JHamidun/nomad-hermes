"""Tests for ``kanban.max_depth`` task-graph depth ceiling."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import kanban_db
from hermes_cli.kanban_db_connect import connect as connect_kanban
from hermes_cli.kanban_db_graph import decompose_triage_task


def _set_kanban_max_depth(monkeypatch: pytest.MonkeyPatch, max_depth: int | None) -> None:
    monkeypatch.setattr(
        "hermes_cli.config.load_config_readonly",
        lambda: {"kanban": {"max_depth": max_depth}},
    )


def test_create_task_rejects_card_deeper_than_kanban_max_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    _set_kanban_max_depth(monkeypatch, 2)

    conn = connect_kanban(tmp_path / "kanban.db")
    try:
        root_id = kanban_db.create_task(conn, title="Root (depth 0)")
        child_id = kanban_db.create_task(conn, title="Child (depth 1)", parents=(root_id,))
        grandchild_id = kanban_db.create_task(
            conn, title="Grandchild (depth 2)", parents=(child_id,)
        )
        assert grandchild_id

        with pytest.raises(ValueError, match=r"kanban\.max_depth \(2\) exceeded"):
            kanban_db.create_task(
                conn, title="Great-grandchild (depth 3)", parents=(grandchild_id,)
            )
    finally:
        conn.close()


def test_link_tasks_rejects_edge_exceeding_kanban_max_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    _set_kanban_max_depth(monkeypatch, 2)

    conn = connect_kanban(tmp_path / "kanban.db")
    try:
        t0 = kanban_db.create_task(conn, title="T0")
        t1 = kanban_db.create_task(conn, title="T1", parents=(t0,))
        t2 = kanban_db.create_task(conn, title="T2")
        t3 = kanban_db.create_task(conn, title="T3", parents=(t2,))

        # Linking t1 (depth 1) -> t2 (has child t3, height 1) would reach depth 1 + 1 + 1 = 3 > 2.
        with pytest.raises(ValueError, match=r"kanban\.max_depth \(2\) exceeded"):
            kanban_db.link_tasks(conn, t1, t2)
    finally:
        conn.close()


def test_decompose_triage_task_rejects_sibling_chain_exceeding_max_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    _set_kanban_max_depth(monkeypatch, 2)

    conn = connect_kanban(tmp_path / "kanban.db")
    try:
        triage_root = kanban_db.create_task(conn, title="Triage root", triage=True)
        # Sibling chain of length 3 (c0 -> c1 -> c2 -> root) reaches depth 3 > 2.
        with pytest.raises(ValueError, match=r"kanban\.max_depth \(2\) exceeded"):
            decompose_triage_task(
                conn,
                triage_root,
                root_assignee="default",
                children=[
                    {"title": "Step 1"},
                    {"title": "Step 2", "parents": [0]},
                    {"title": "Step 3", "parents": [1]},
                ],
            )
    finally:
        conn.close()


def test_unset_kanban_max_depth_allows_arbitrary_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))
    _set_kanban_max_depth(monkeypatch, None)

    conn = connect_kanban(tmp_path / "kanban.db")
    try:
        cur = kanban_db.create_task(conn, title="Depth 0")
        for depth in range(1, 5):
            cur = kanban_db.create_task(conn, title=f"Depth {depth}", parents=(cur,))
        assert kanban_db._ancestor_depth(conn, cur) == 4
    finally:
        conn.close()
