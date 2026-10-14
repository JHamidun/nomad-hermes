"""Tests for HelpTip component and the 14 desktop screen placements."""

from __future__ import annotations

from pathlib import Path

DESKTOP_SRC = Path(__file__).resolve().parents[2] / "apps" / "desktop" / "src"

FOURTEEN_SURFACES = [
    "app/chat/composer/model-pill.tsx",
    "app/settings/appearance-settings.tsx",
    "app/settings/config-settings.tsx",
    "app/settings/env-credentials.tsx",
    "app/settings/gateway-settings.tsx",
    "app/settings/keys-settings.tsx",
    "app/capabilities/mcp/mcp-editor.tsx",
    "app/settings/model-settings.tsx",
    "app/settings/notifications-settings.tsx",
    "app/settings/primitives.tsx",
    "app/settings/providers-settings.tsx",
    "app/capabilities/skills/skills-tab.tsx",
    "components/model-picker.tsx",
    "components/onboarding/index.tsx",
]


def test_help_tip_component_exists():
    help_tip = DESKTOP_SRC / "components" / "ui" / "help-tip.tsx"
    assert help_tip.is_file()
    src = help_tip.read_text(encoding="utf-8")
    assert "export function HelpTip(" in src
    assert 'data-slot="help-tip-trigger"' in src
    assert 'data-slot="help-tip-content"' in src


def test_all_fourteen_desktop_surfaces_wire_help_tip():
    assert len(FOURTEEN_SURFACES) == 14
    for rel in FOURTEEN_SURFACES:
        path = DESKTOP_SRC / rel
        assert path.is_file(), f"missing surface: {rel}"
        src = path.read_text(encoding="utf-8")
        assert "HelpTip" in src or "help={" in src, f"{rel} does not wire HelpTip"
