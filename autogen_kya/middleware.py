"""Middleware — @kya_verified decorator and GroupChat message filter for AutoGen.

Wraps AutoGen agent callbacks or any callable to require KYA identity
verification before the function body executes. Also provides a
GroupChat-compatible message filter.
"""

from __future__ import annotations

import functools
import json
from typing import Any, Callable, Dict, List, Optional

from autogen_kya.card import get_card
from autogen_kya.identity import _verify_card_data


class KYAVerificationError(Exception):
    """Raised when an agent fails KYA identity verification."""

    def __init__(self, agent_name: str, reason: str):
        self.agent_name = agent_name
        self.reason = reason
        super().__init__(f"KYA verification failed for '{agent_name}': {reason}")


def kya_verified(
    min_score: int = 0,
    require_signature: bool = False,
    required_capabilities: Optional[list[str]] = None,
    on_fail: str = "raise",
) -> Callable:
    """Decorator that gates a function on KYA identity verification.

    The decorated function must receive an `agent` keyword argument
    (or first positional argument) that has a _kya_card attached via
    `attach_card()`.

    AutoGen agents have a `name` attribute (not `role` like CrewAI),
    so detection checks for `name` and `system_message`.

    Args:
        min_score: Minimum completeness score (0-100). Default 0 (any valid card).
        require_signature: Require a verified Ed25519 signature.
        required_capabilities: List of capability names the agent must declare.
        on_fail: "raise" (default) raises KYAVerificationError.
                 "skip" returns None silently. "log" prints a warning and continues.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Try to find the agent from args
            agent = kwargs.get("agent")
            if agent is None and args:
                candidate = args[0]
                if hasattr(candidate, "name") and (
                    hasattr(candidate, "system_message") or hasattr(candidate, "_kya_card")
                ):
                    agent = candidate

            if agent is None:
                return _handle_fail(
                    "unknown",
                    "No agent found — pass agent as first arg or 'agent' kwarg",
                    on_fail,
                    func,
                    args,
                    kwargs,
                )

            card = get_card(agent)
            if card is None:
                agent_name = getattr(agent, "name", str(agent))
                return _handle_fail(
                    agent_name,
                    "No KYA card attached. Use attach_card(agent, card) first.",
                    on_fail,
                    func,
                    args,
                    kwargs,
                )

            # Run verification
            result = _verify_card_data(card)
            agent_name = result.get("agent_name", "unknown")

            if not result["valid"]:
                return _handle_fail(
                    agent_name,
                    f"Card validation failed: {'; '.join(result['errors'])}",
                    on_fail,
                    func,
                    args,
                    kwargs,
                )

            # Score check
            if result["completeness_score"] < min_score:
                return _handle_fail(
                    agent_name,
                    f"Score {result['completeness_score']}/100 below required {min_score}",
                    on_fail,
                    func,
                    args,
                    kwargs,
                )

            # Signature check
            if require_signature:
                sig_status = result.get("signature", {}).get("status", "unsigned")
                if sig_status != "verified":
                    return _handle_fail(
                        agent_name,
                        f"Signature status: {sig_status} (verified required)",
                        on_fail,
                        func,
                        args,
                        kwargs,
                    )

            # Capabilities check
            if required_capabilities:
                declared = set(result.get("capabilities", []))
                declared_lower = {c.lower() for c in declared}
                missing = [
                    c for c in required_capabilities
                    if c.lower() not in declared_lower
                ]
                if missing:
                    return _handle_fail(
                        agent_name,
                        f"Missing capabilities: {', '.join(missing)}",
                        on_fail,
                        func,
                        args,
                        kwargs,
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def kya_groupchat_filter(
    agents: List[Any],
    min_score: int = 0,
    require_card: bool = True,
) -> List[Any]:
    """Filter a list of AutoGen agents for GroupChat, keeping only verified ones.

    Use this to gate which agents are allowed into a GroupChat based on
    their KYA identity cards.

    Args:
        agents: List of AutoGen agent instances.
        min_score: Minimum completeness score required.
        require_card: If True, agents without cards are excluded.

    Returns:
        Filtered list of agents that pass verification.
    """
    verified = []
    for agent in agents:
        card = get_card(agent)
        if card is None:
            if not require_card:
                verified.append(agent)
            continue

        result = _verify_card_data(card)
        if result["valid"] and result["completeness_score"] >= min_score:
            verified.append(agent)

    return verified


def _handle_fail(
    agent_name: str,
    reason: str,
    on_fail: str,
    func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Handle a verification failure according to the on_fail policy."""
    if on_fail == "raise":
        raise KYAVerificationError(agent_name, reason)
    elif on_fail == "skip":
        return None
    elif on_fail == "log":
        import sys

        print(
            f"[autogen-kya] WARNING: {agent_name} — {reason}",
            file=sys.stderr,
        )
        return func(*args, **kwargs)
    else:
        raise KYAVerificationError(agent_name, reason)
