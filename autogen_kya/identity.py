"""KYA identity verification — AutoGen-compatible tool functions.

In AutoGen, tools are plain functions registered via register_function().
This module provides kya_verify_identity() as a registerable tool function.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _verify_card_data(card: Dict[str, Any], public_key_path: Optional[str] = None) -> Dict[str, Any]:
    """Core verification logic, independent of AutoGen."""
    from kya.validator import (
        validate_required_fields,
        validate_capabilities,
        compute_completeness_score,
        load_schema,
    )

    schema = load_schema()

    errors = validate_required_fields(card, schema)
    errors.extend([
        e for e in validate_capabilities(card)
        if "missing" in e.lower()
    ])

    score = compute_completeness_score(card)

    # Check signature if present
    sig_result: Dict[str, Any] = {"status": "unsigned"}
    if "_signature" in card:
        try:
            from kya.signer import verify_card

            sig_result_raw = verify_card(card, public_key_path=public_key_path)
            if sig_result_raw.get("valid"):
                sig_result = {
                    "status": "verified",
                    "key_id": sig_result_raw["key_id"],
                    "signed_at": sig_result_raw["signed_at"],
                    "algorithm": sig_result_raw["algorithm"],
                }
            else:
                sig_result = {
                    "status": "invalid",
                    "error": sig_result_raw.get("error", "verification failed"),
                }
        except ImportError:
            sig_result = {
                "status": "unverified",
                "note": "Install kya-agent[signing] to verify signatures",
            }

    result = {
        "valid": len(errors) == 0,
        "agent_id": card.get("agent_id", "unknown"),
        "agent_name": card.get("name", "unknown"),
        "completeness_score": score,
        "signature": sig_result,
        "capabilities": [
            c.get("name", "unnamed")
            for c in card.get("capabilities", {}).get("declared", [])
        ],
        "errors": errors,
    }

    return result


def kya_verify_identity(card_json: str, public_key_path: Optional[str] = None) -> str:
    """Verify a KYA agent identity card.

    This function is designed to be registered as an AutoGen tool via
    register_function(). It takes a JSON string of a KYA card and returns
    a human-readable verification result.

    Args:
        card_json: JSON string of a KYA agent identity card to verify.
        public_key_path: Optional path to a PEM public key file for signature verification.

    Returns:
        Human-readable verification result string.
    """
    try:
        card = json.loads(card_json)
    except json.JSONDecodeError as e:
        return f"FAILED: Invalid JSON — {e}"

    result = _verify_card_data(card, public_key_path)

    lines = []
    status = "VERIFIED" if result["valid"] else "FAILED"
    lines.append(f"Identity: {status}")
    lines.append(f"Agent: {result['agent_name']} ({result['agent_id']})")
    lines.append(f"Completeness: {result['completeness_score']}/100")
    lines.append(f"Signature: {result['signature']['status']}")

    if result["capabilities"]:
        lines.append(f"Capabilities: {', '.join(result['capabilities'])}")

    if result["errors"]:
        lines.append(f"Errors: {'; '.join(result['errors'])}")

    return "\n".join(lines)
