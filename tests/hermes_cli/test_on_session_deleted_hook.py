"""Tests for the ``on_session_deleted`` plugin lifecycle hook."""

from __future__ import annotations

from pathlib import Path

from hermes_cli import lifecycle, plugins
from hermes_state import SessionDB


def test_on_session_deleted_is_in_valid_hooks() -> None:
    assert "on_session_deleted" in plugins.VALID_HOOKS


def test_delete_session_invokes_on_session_deleted_hook_with_session_id(
    tmp_path: Path, monkeypatch
) -> None:
    deleted_ids: list[str] = []

    monkeypatch.setattr(
        lifecycle,
        "has_hook",
        lambda name: name == "on_session_deleted",
    )
    monkeypatch.setattr(
        lifecycle,
        "invoke_hook",
        lambda name, **kwargs: deleted_ids.append(str(kwargs.get("session_id")))
        if name == "on_session_deleted"
        else None,
    )

    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        db.create_session(session_id="sess_del_1", source="cli", model="test-model")
        assert db.delete_session("sess_del_1") is True
        assert deleted_ids == ["sess_del_1"]

        # Deleting a non-existent session does not fire the hook.
        assert db.delete_session("sess_nonexistent") is False
        assert deleted_ids == ["sess_del_1"]
    finally:
        db.close()


def test_delete_sessions_bulk_invokes_on_session_deleted_for_each_removed_id(
    tmp_path: Path, monkeypatch
) -> None:
    deleted_ids: list[str] = []

    monkeypatch.setattr(
        lifecycle,
        "has_hook",
        lambda name: name == "on_session_deleted",
    )
    monkeypatch.setattr(
        lifecycle,
        "invoke_hook",
        lambda name, **kwargs: deleted_ids.append(str(kwargs.get("session_id")))
        if name == "on_session_deleted"
        else None,
    )

    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        db.create_session(session_id="sess_b1", source="cli", model="test-model")
        db.create_session(session_id="sess_b2", source="cli", model="test-model")
        count = db.delete_sessions(["sess_b1", "sess_b2", "sess_missing"])
        assert count == 2
        assert sorted(deleted_ids) == ["sess_b1", "sess_b2"]
    finally:
        db.close()
