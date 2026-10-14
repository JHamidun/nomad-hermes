"""Tests for runtime billing provider registration in agent/billing_links.py."""

from __future__ import annotations

from agent.billing_links import (
    build_billing_block,
    register_billing_provider,
    unregister_billing_provider,
)


def test_register_and_resolve_custom_billing_provider_by_slug_and_host():
    try:
        register_billing_provider(
            "acme-cloud",
            "Acme Cloud",
            "https://billing.acme.example/topup",
            hosts=("api.acme.example",),
        )
        by_slug = build_billing_block(
            provider="acme-cloud",
            base_url="https://custom.local/v1",
            model="acme-large",
        )
        assert by_slug.provider_label == "Acme Cloud"
        assert by_slug.billing_url == "https://billing.acme.example/topup"
        assert by_slug.is_nous is False

        by_host = build_billing_block(
            provider="custom",
            base_url="https://api.acme.example/v1",
            model="acme-large",
        )
        assert by_host.provider_label == "Acme Cloud"
        assert by_host.billing_url == "https://billing.acme.example/topup"
    finally:
        unregister_billing_provider("acme-cloud")

    fallback = build_billing_block(
        provider="acme-cloud",
        base_url="https://api.acme.example/v1",
        model="acme-large",
    )
    assert fallback.billing_url is None
