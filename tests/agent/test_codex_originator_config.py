"""Tests for codex_cloudflare_headers honouring model.default_headers."""

from __future__ import annotations

import agent.auxiliary_client as aux_mod
from agent.codex_headers import CODEX_AUX_BASE_URL, apply_required_codex_headers, codex_cloudflare_headers


def test_codex_headers_default_when_no_user_headers(monkeypatch):
    monkeypatch.setattr(aux_mod, "_apply_user_default_headers", lambda d: dict(d))
    headers = codex_cloudflare_headers("", base_url=CODEX_AUX_BASE_URL)
    assert headers["originator"] == "hermes-agent"
    assert headers["User-Agent"].startswith("HermesAgent/")


def test_codex_headers_honours_explicit_originator_and_user_agent(monkeypatch):
    monkeypatch.setattr(
        aux_mod,
        "_apply_user_default_headers",
        lambda d: {**d, "User-Agent": "CustomHarness/1.2.3", "originator": "custom-harness"},
    )
    headers = codex_cloudflare_headers("", base_url=CODEX_AUX_BASE_URL)
    assert headers["User-Agent"] == "CustomHarness/1.2.3"
    assert headers["originator"] == "custom-harness"


def test_codex_headers_derives_originator_from_x_title(monkeypatch):
    monkeypatch.setattr(
        aux_mod,
        "_apply_user_default_headers",
        lambda d: {**d, "User-Agent": "AcmeClient/2.0", "X-Title": "Acme"},
    )
    client_kwargs = {"default_headers": {"X-Custom": "1"}}
    apply_required_codex_headers(client_kwargs, access_token="", base_url=CODEX_AUX_BASE_URL)
    assert client_kwargs["default_headers"]["User-Agent"] == "AcmeClient/2.0"
    assert client_kwargs["default_headers"]["originator"] == "acme-agent"
    assert client_kwargs["default_headers"]["X-Custom"] == "1"
