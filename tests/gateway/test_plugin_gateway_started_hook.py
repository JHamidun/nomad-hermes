"""Tests for the gateway_started plugin hook in VALID_HOOKS and GatewayStartupMixin."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gateway.config import Platform
from gateway.run_startup import GatewayStartupMixin
from hermes_cli import plugins


def test_gateway_started_in_valid_hooks():
    assert "gateway_started" in plugins.VALID_HOOKS


def test_start_post_connect_services_invokes_gateway_started_hook(monkeypatch, tmp_path):
    fired: list[dict] = []

    def fake_invoke_hook(event: str, **kwargs):
        if event == "gateway_started":
            fired.append(kwargs)
        return []

    async def _noop_async(*args, **kwargs):
        return None

    async def _empty_dir(*args, **kwargs):
        return {"platforms": {}}

    async def _no_update(*args, **kwargs):
        return False

    monkeypatch.setattr("hermes_cli.lifecycle.invoke_hook", fake_invoke_hook)
    monkeypatch.setattr("gateway.run._hermes_home", tmp_path, raising=False)
    monkeypatch.setattr(
        "gateway.run_heartbeat_restore.restore_heartbeat_watches",
        _noop_async,
    )
    monkeypatch.setattr(
        "gateway.channel_directory.build_channel_directory",
        _empty_dir,
    )

    class _DummyGateway(GatewayStartupMixin):
        def __init__(self):
            self.adapters = {Platform.TELEGRAM: object()}
            self.hooks = SimpleNamespace(loaded_hooks=[], emit=_noop_async)

        async def _ensure_hosted_room_worker(self):
            return None

        def _spawn_supervised(self, *args, **kwargs):
            return None

        def _start_loop_heartbeat_task(self):
            return None

        def _start_heartbeat_poller(self):
            return None

        async def _send_update_notification(self):
            return False

        def _schedule_update_notification_watch(self):
            return None

    gw = _DummyGateway()
    asyncio.run(gw._start_post_connect_services(connected_count=1))

    assert len(fired) == 1
    assert fired[0]["platforms"] == ["telegram"]
    assert fired[0]["connected_count"] == 1
    assert fired[0]["gateway"] is gw
