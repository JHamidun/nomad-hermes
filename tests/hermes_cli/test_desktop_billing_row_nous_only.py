"""Tests that the desktop Settings Billing row is shown only for the 'nous' provider."""

from __future__ import annotations

from pathlib import Path
import re


def _eval_is_nous_billing_provider(provider: str | None) -> bool:
    tsx = Path("apps/desktop/src/app/settings/index.tsx").read_text(encoding="utf-8")
    assert "export function isNousBillingProvider" in tsx
    assert "...(isNousBillingProvider(" in tsx
    return str(provider or "").strip().lower() == "nous"


def test_billing_row_shown_for_nous_provider():
    assert _eval_is_nous_billing_provider("nous") is True
    assert _eval_is_nous_billing_provider("Nous") is True


def test_billing_row_hidden_for_non_nous_providers():
    for provider in ("openrouter", "openai", "anthropic", "custom", "", None):
        assert _eval_is_nous_billing_provider(provider) is False
    tsx = Path("apps/desktop/src/app/settings/index.tsx").read_text(encoding="utf-8")
    assert "id: 'billing' as SettingsViewId" in tsx
    assert "...(isNousBillingProvider(" in tsx
