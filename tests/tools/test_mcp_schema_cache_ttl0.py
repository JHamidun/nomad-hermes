"""Tests for MCP schema cache handling of ttl_ms=0 (D03)."""

from __future__ import annotations

from pathlib import Path

import tools.mcp_schema_cache as cache_mod
from tools.mcp_schema_cache import config_fingerprint, get_cached_entry, write_cache_entry


def test_ttl_ms_zero_does_not_immediately_expire_cache_entry(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_cache_path", lambda: tmp_path / "mcp_schema_cache.json")
    fp = config_fingerprint({"command": "npx", "args": ["-y", "demo-mcp"]})
    tools = [{"name": "ping", "description": "Ping tool", "inputSchema": {"type": "object"}}]

    write_cache_entry("demo", fp, tools=tools, ttl_ms=0)
    cached = get_cached_entry("demo", fp)
    assert cached is not None
    assert cached["tools"] == tools
    assert "ttl_ms" not in cached


def test_positive_ttl_ms_still_expires_after_deadline(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_cache_path", lambda: tmp_path / "mcp_schema_cache.json")
    fp = config_fingerprint({"command": "npx", "args": ["-y", "demo-mcp"]})
    tools = [{"name": "ping", "description": "Ping tool", "inputSchema": {"type": "object"}}]

    now = [1000.0]
    monkeypatch.setattr(cache_mod.time, "time", lambda: now[0])
    write_cache_entry("demo", fp, tools=tools, ttl_ms=5000)

    now[0] = 1002.0
    assert get_cached_entry("demo", fp) is not None

    now[0] = 1006.0
    assert get_cached_entry("demo", fp) is None
