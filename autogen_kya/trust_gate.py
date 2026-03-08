"""TrustGateTool — Gate agent actions on trust score thresholds.

An AutoGen-compatible tool function that checks whether an agent's KYA
identity card meets a minimum completeness/trust score before allowing
an action to proceed.
"""

from __future__ import annotations

import json
from typing import Optional


def kya_trust_gate(
    card_json: str,
    min_score: int = 50,
    require_signature: bool = False,
    required_capabilities: Optional[str] = None,
) -> str:
    """Evaluate whether a KYA card meets trust requirements.

    Designed to be registered as an AutoGen tool via register_function().

    Args:
        card_json: JSON string of a KYA agent identity card.
        min_score: Minimum completeness score (0-100) required to pass.
        require_signature: If true, the card must have a valid Ed25519 signature.
        required_capabilities: Comma-separated list of capability names the agent must declare.

    Returns:
        Human-readable PASS/FAIL result with reasons.
    """
    try:
        card = json.loads(card_json)
    except json.JSONDecodeError as e:
        return f"BLOCKED: Invalid JSON — {e}"

    from kya.validator import compute_completeness_score

    score = compute_completeness_score(card)
    reasons: list[str] = []
    passed = True

    # Score check
    if score < min_score:
        passed = False
        reasons.append(f"Score {score}/100 below threshold {min_score}")

    # Signature check
    if require_signature:
        sig = card.get("_signature")
        if not sig:
            passed = False
            reasons.append("No signature — card is unsigned")
        else:
            try:
                from kya.signer import verify_card

                result = verify_card(card)
                if not result.get("valid"):
                    passed = False
                    reasons.append(f"Invalid signature: {result.get('error', 'unknown')}")
            except ImportError:
                passed = False
                reasons.append("Cannot verify signature — install kya-agent[signing]")

    # Capabilities check
    if required_capabilities:
        required = {c.strip().lower() for c in required_capabilities.split(",")}
        declared = {
            c.get("name", "").lower()
            for c in card.get("capabilities", {}).get("declared", [])
        }
        missing = required - declared
        if missing:
            passed = False
            reasons.append(f"Missing capabilities: {', '.join(sorted(missing))}")

    # Build result
    agent_name = card.get("name", "unknown")
    agent_id = card.get("agent_id", "unknown")

    lines = []
    if passed:
        lines.append(f"PASSED: {agent_name} ({agent_id})")
        lines.append(f"Score: {score}/100")
        lines.append("Action permitted.")
    else:
        lines.append(f"BLOCKED: {agent_name} ({agent_id})")
        lines.append(f"Score: {score}/100")
        for r in reasons:
            lines.append(f"Reason: {r}")
        lines.append("Action denied.")

    return "\n".join(lines)
