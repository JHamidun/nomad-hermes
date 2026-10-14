"""Tests for configurable .brand wordmark on the /login page."""

from __future__ import annotations

from dataclasses import dataclass

from hermes_cli.dashboard_auth import login_page


@dataclass
class _DummyProvider:
    name: str = "password"
    display_name: str = "Password"
    supports_password: bool = True


def test_login_page_defaults_to_nous_research_brand(monkeypatch):
    monkeypatch.setattr(login_page, "list_session_providers", lambda: [_DummyProvider()])
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    rendered = login_page.render_login_html()
    assert '<div class="brand">Nous<span class="dot"></span>Research</div>' in rendered


def test_login_page_uses_custom_login_brand(monkeypatch):
    monkeypatch.setattr(login_page, "list_session_providers", lambda: [_DummyProvider()])
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"branding": {"login_brand": "Acme Studio"}},
    )
    rendered = login_page.render_login_html()
    assert '<div class="brand">Acme Studio</div>' in rendered
    assert 'Nous<span class="dot"></span>Research' not in rendered


def test_login_page_escapes_html_in_custom_brand(monkeypatch):
    monkeypatch.setattr(login_page, "list_session_providers", lambda: [_DummyProvider()])
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"branding": {"agent_name": "Lab <One> & Co"}},
    )
    rendered = login_page.render_login_html()
    assert '<div class="brand">Lab &lt;One&gt; &amp; Co</div>' in rendered
