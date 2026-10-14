"""Tests for core USD spend ceiling (budget.max_usd)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.error_classifier import FailoverReason
from agent.turn_api_call import nous_rate_limit_guard
from agent.usage_budget import (
    UsageBudgetExceededError,
    check_usd_budget,
    enforce_usd_budget,
    resolve_max_usd_budget,
)
from hermes_cli.config_defaults import DEFAULT_CONFIG


def test_default_config_declares_budget_max_usd():
    assert "budget" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["budget"]["max_usd"] is None


def test_resolve_max_usd_budget_from_config():
    cfg = {"budget": {"max_usd": 1.25}}
    assert resolve_max_usd_budget(config=cfg) == pytest.approx(1.25)
    assert resolve_max_usd_budget(config={"budget": {"max_usd": None}}) is None


def test_check_and_enforce_usd_budget_refuses_with_classified_error():
    agent = SimpleNamespace(
        provider="openrouter",
        model="anthropic/claude-sonnet-4",
        session_estimated_cost_usd=0.55,
        config={"budget": {"max_usd": 0.50}},
    )
    classified = check_usd_budget(agent)
    assert classified is not None
    assert classified.reason is FailoverReason.billing
    assert classified.status_code == 402
    assert classified.retryable is False
    assert classified.should_fallback is False
    assert classified.should_rotate_credential is False
    assert classified.error_context["spent_usd"] == pytest.approx(0.55)
    assert classified.error_context["max_usd"] == pytest.approx(0.50)

    with pytest.raises(UsageBudgetExceededError) as exc_info:
        enforce_usd_budget(agent)
    assert exc_info.value.classified.reason is FailoverReason.billing
    assert exc_info.value.classified.retryable is False


def test_turn_guard_blocks_next_call_when_budget_max_usd_exhausted():
    persisted: list[tuple] = []
    agent = SimpleNamespace(
        provider="openai",
        model="gpt-5.4",
        session_estimated_cost_usd=2.00,
        config={"budget": {"max_usd": 2.00}},
        _flush_status_buffer=lambda: None,
        _persist_session=lambda m, h: persisted.append((m, h)),
    )
    verdict = nous_rate_limit_guard(
        agent,
        _retry=SimpleNamespace(),
        api_messages=[],
        messages=[{"role": "user", "content": "next turn"}],
        conversation_history=[],
        active_system_prompt="sys",
        retry_count=0,
        compression_attempts=0,
        api_call_count=3,
    )
    assert verdict.action == "return"
    assert verdict.result is not None
    assert verdict.result["failed"] is True
    assert verdict.result["completed"] is False
    assert verdict.result["failure_reason"] == "billing"
    assert verdict.result["failure_retryable"] is False
    assert verdict.result["classified_error"].reason is FailoverReason.billing
    assert len(persisted) == 1
