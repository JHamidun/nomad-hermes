"""Tests for branding.release_notes_url in CLI banner and desktop update-status."""

from __future__ import annotations

from pathlib import Path

import hermes_cli.banner as banner_mod
import hermes_cli.config as cfg_mod
import hermes_cli.skin_engine as skin_mod


class _DummySkin:
    def __init__(self, release_notes_url: str = ""):
        self._url = release_notes_url

    def get_branding(self, key: str, fallback: str = "") -> str:
        if key == "release_notes_url" and self._url:
            return self._url
        return fallback


def test_banner_release_notes_url_defaults_to_stock_when_unset(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(banner_mod, "_latest_release_cache", None, raising=False)
    monkeypatch.setattr(skin_mod, "get_active_skin", lambda: _DummySkin(""))
    monkeypatch.setattr(cfg_mod, "load_config", lambda: {})
    monkeypatch.setattr(banner_mod.source_check, "_git_stdout", lambda args, **kw: "v0.21.7")

    tag, url = banner_mod.get_latest_release_tag(repo_dir=tmp_path)
    assert tag == "v0.21.7"
    assert url == "https://github.com/NousResearch/hermes-agent/releases/tag/v0.21.7"


def test_banner_release_notes_url_uses_branding_key_when_set(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(banner_mod, "_latest_release_cache", None, raising=False)
    monkeypatch.setattr(skin_mod, "get_active_skin", lambda: _DummySkin(""))
    monkeypatch.setattr(
        cfg_mod,
        "load_config",
        lambda: {"branding": {"release_notes_url": "https://github.com/acme/custom-agent/releases"}},
    )
    monkeypatch.setattr(banner_mod.source_check, "_git_stdout", lambda args, **kw: "v0.21.7")

    tag, url = banner_mod.get_latest_release_tag(repo_dir=tmp_path)
    assert tag == "v0.21.7"
    assert url == "https://github.com/acme/custom-agent/releases/tag/v0.21.7"


def test_desktop_update_status_exports_resolve_release_notes_url():
    tsx = Path("apps/desktop/src/components/update-status.tsx").read_text(encoding="utf-8")
    assert "export function resolveReleaseNotesUrl" in tsx
    assert "config?.branding?.release_notes_url" in tsx
    assert "RELEASE_NOTES_URL = 'https://github.com/NousResearch/hermes-agent/releases'" in tsx
