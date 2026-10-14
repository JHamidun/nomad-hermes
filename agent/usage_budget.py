"""Core USD spend ceiling (``budget.max_usd``) for agent turns and sessions.

When ``budget.max_usd`` (or ``agent.max_usd``) is configured to a positive float
and the session's accumulated estimated cost reaches or exceeds that ceiling,
the next API call is refused before hitting the provider with a deterministic
``ClassifiedError(reason=FailoverReason.billing, retryable=False)``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from agent.error_classifier import ClassifiedError, FailoverReason
from agent.turn_failure_copy import stamp_failure


class UsageBudgetExceededError(RuntimeError):
    """Raised when the session's USD spend reaches or exceeds ``budget.max_usd``."""

    def __init__(self, classified: ClassifiedError, *, spent_usd: float, max_usd: float) -> None:
        super().__init__(classified.message)
        self.classified = classified
        self.reason = classified.reason
        self.spent_usd = float(spent_usd)
        self.max_usd = float(max_usd)


def _coerce_positive_usd(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or raw.lower() in {"none", "null", "unlimited", "inf", "off"}:
            return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0.0 else None


def resolve_max_usd_budget(
    config: Optional[Mapping[str, Any]] = None,
    agent: Any = None,
) -> Optional[float]:
    """Resolve the active ``budget.max_usd`` ceiling from explicit args, ``agent``, or runtime config."""
    if agent is not None:
        for attr in ("budget_max_usd", "max_usd"):
            direct = _coerce_positive_usd(getattr(agent, attr, None))
            if direct is not None:
                return direct
        if config is None:
            agent_cfg = getattr(agent, "config", None) or getattr(agent, "_config", None)
            if isinstance(agent_cfg, Mapping):
                config = agent_cfg

    if config is None:
        try:
            from hermes_cli.config import load_config

            loaded = load_config()
            if isinstance(loaded, Mapping):
                config = loaded
        except Exception:
            config = None

    if isinstance(config, Mapping):
        budget_block = config.get("budget")
        if isinstance(budget_block, Mapping):
            val = _coerce_positive_usd(budget_block.get("max_usd"))
            if val is not None:
                return val
        agent_block = config.get("agent")
        if isinstance(agent_block, Mapping):
            val = _coerce_positive_usd(agent_block.get("max_usd"))
            if val is not None:
                return val
        top_val = _coerce_positive_usd(config.get("max_usd"))
        if top_val is not None:
            return top_val

    return None


def resolve_spent_usd(agent: Any = None, spent_usd: Optional[float] = None) -> float:
    """Return accumulated session spend in USD from explicit override or ``agent``."""
    if spent_usd is not None and not isinstance(spent_usd, bool):
        try:
            return max(0.0, float(spent_usd))
        except (TypeError, ValueError):
            return 0.0
    if agent is None:
        return 0.0
    for attr in ("session_estimated_cost_usd", "estimated_cost_usd", "spent_usd"):
        raw = getattr(agent, attr, None)
        if raw is not None and not isinstance(raw, bool):
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                continue
    return 0.0


def classify_budget_exhausted(
    spent_usd: float,
    max_usd: float,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> ClassifiedError:
    """Build a non-retryable ``ClassifiedError`` for an exhausted USD spend budget."""
    spent = float(spent_usd)
    ceiling = float(max_usd)
    msg = (
        f"USD spend budget exhausted: session spend ${spent:.4f} has reached "
        f"budget.max_usd (${ceiling:.4f})."
    )
    return ClassifiedError(
        reason=FailoverReason.billing,
        status_code=402,
        provider=provider,
        model=model,
        message=msg,
        error_context={
            "budget_key": "budget.max_usd",
            "spent_usd": spent,
            "max_usd": ceiling,
        },
        retryable=False,
        should_compress=False,
        should_rotate_credential=False,
        should_fallback=False,
    )


def check_usd_budget(
    agent: Any = None,
    *,
    spent_usd: Optional[float] = None,
    max_usd: Optional[float] = None,
    config: Optional[Mapping[str, Any]] = None,
    raise_on_exceeded: bool = False,
) -> Optional[ClassifiedError]:
    """Return ``ClassifiedError`` when ``spent_usd >= max_usd``, or ``None`` when allowed."""
    ceiling = _coerce_positive_usd(max_usd) if max_usd is not None else resolve_max_usd_budget(config=config, agent=agent)
    if ceiling is None:
        return None
    spent = resolve_spent_usd(agent=agent, spent_usd=spent_usd)
    if spent < ceiling:
        return None
    classified = classify_budget_exhausted(
        spent,
        ceiling,
        provider=getattr(agent, "provider", None) if agent is not None else None,
        model=getattr(agent, "model", None) if agent is not None else None,
    )
    if raise_on_exceeded:
        raise UsageBudgetExceededError(classified, spent_usd=spent, max_usd=ceiling)
    return classified


def enforce_usd_budget(
    agent: Any = None,
    *,
    spent_usd: Optional[float] = None,
    max_usd: Optional[float] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> None:
    """Raise :class:`UsageBudgetExceededError` if the USD spend ceiling has been reached."""
    check_usd_budget(
        agent,
        spent_usd=spent_usd,
        max_usd=max_usd,
        config=config,
        raise_on_exceeded=True,
    )


def budget_turn_failure_result(
    agent: Any,
    classified: ClassifiedError,
    *,
    messages: Any = None,
    conversation_history: Any = None,
    api_call_count: int = 0,
) -> dict[str, Any]:
    """Format a turn-ending failure dict when ``budget.max_usd`` blocks the next API call."""
    if agent is not None:
        try:
            agent._flush_status_buffer()
        except Exception:
            pass
        try:
            agent._persist_session(messages, conversation_history)
        except Exception:
            pass
    return stamp_failure(
        {
            "final_response": f"❌ {classified.message}",
            "messages": messages if messages is not None else [],
            "api_calls": api_call_count,
            "completed": False,
            "failed": True,
            "error": classified.message,
            "classified_error": classified,
        },
        FailoverReason.billing.value,
        False,
    )
