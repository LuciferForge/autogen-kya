"""Card helpers — create and manage KYA identity cards for AutoGen agents.

Works with or without pyautogen installed. When pyautogen is available, cards
are stored on agent objects via a _kya_card attribute.

AutoGen agents (ConversableAgent, AssistantAgent, UserProxyAgent) expose:
    - name: str
    - system_message: str | list
    - llm_config: dict | None
    - description: str
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional


def _resolve_agent_fields(agent: Any) -> Dict[str, str]:
    """Extract identity-relevant fields from an AutoGen agent object."""
    name = getattr(agent, "name", "unknown-agent")
    system_message = getattr(agent, "system_message", "")
    description = getattr(agent, "description", "")
    llm_config = getattr(agent, "llm_config", {}) or {}

    # If system_message is a list (chat-format), join it
    if isinstance(system_message, list):
        system_message = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in system_message
        )

    # Extract model name from llm_config if available
    model = ""
    if isinstance(llm_config, dict):
        config_list = llm_config.get("config_list", [])
        if config_list and isinstance(config_list, list):
            model = config_list[0].get("model", "")

    # Build a stable slug from the name
    slug = name.lower().replace(" ", "-").replace("_", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = slug.strip("-") or "agent"

    return {
        "name": name,
        "system_message": str(system_message),
        "description": str(description),
        "model": model,
        "slug": slug,
    }


def _extract_tool_capabilities(agent: Any) -> List[Dict[str, str]]:
    """Extract capabilities from an AutoGen agent's registered functions.

    AutoGen agents register tools via register_function() or function_map.
    We inspect _function_map if available.
    """
    func_map = getattr(agent, "_function_map", None) or {}
    capabilities = []
    for func_name, func in func_map.items():
        doc = getattr(func, "__doc__", "") or ""
        capabilities.append({
            "name": func_name,
            "description": doc[:200],
            "risk_level": "medium",
            "scope": "as-configured",
        })
    return capabilities


def create_agent_card(
    agent: Any,
    *,
    owner_name: str = "unspecified",
    owner_contact: str = "unspecified",
    agent_id_prefix: str = "autogen",
    capabilities: Optional[List[Dict[str, str]]] = None,
    version: str = "0.1.0",
    risk_classification: str = "minimal",
    human_oversight: str = "human-on-the-loop",
) -> Dict[str, Any]:
    """Create a KYA identity card from an AutoGen agent.

    Args:
        agent: An autogen ConversableAgent/AssistantAgent/UserProxyAgent instance
               (or any object with name/system_message/llm_config/description).
        owner_name: Organization or person responsible for this agent.
        owner_contact: Contact email for security/compliance inquiries.
        agent_id_prefix: Prefix for the agent_id (default: "autogen").
        capabilities: Override auto-detected capabilities. If None, extracted from agent.
        version: Semantic version for the agent.
        risk_classification: EU AI Act risk level (minimal/limited/high/unacceptable).
        human_oversight: Oversight level.

    Returns:
        A KYA card dict conforming to the v0.1 schema.
    """
    fields = _resolve_agent_fields(agent)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if capabilities is None:
        capabilities = _extract_tool_capabilities(agent)

    # Build purpose from description + system_message
    purpose_parts = []
    if fields["description"]:
        purpose_parts.append(fields["description"])
    if fields["system_message"]:
        purpose_parts.append(fields["system_message"])
    purpose = ". ".join(purpose_parts) if purpose_parts else f"AutoGen agent: {fields['name']}"
    # Ensure purpose meets KYA minLength of 10
    if len(purpose) < 10:
        purpose = f"AutoGen agent performing the role of {fields['name']}"
    # Cap at schema maxLength
    purpose = purpose[:500]

    card: Dict[str, Any] = {
        "kya_version": "0.1",
        "agent_id": f"{agent_id_prefix}/{fields['slug']}",
        "name": fields["name"],
        "version": version,
        "purpose": purpose,
        "agent_type": "autonomous",
        "owner": {
            "name": owner_name,
            "contact": owner_contact,
        },
        "capabilities": {
            "declared": capabilities,
            "denied": [],
        },
        "data_access": {
            "sources": [],
            "destinations": [],
            "pii_handling": "none",
            "retention_policy": "session-only",
        },
        "security": {
            "last_audit": None,
            "known_vulnerabilities": [],
            "injection_tested": False,
        },
        "compliance": {
            "frameworks": [],
            "risk_classification": risk_classification,
            "human_oversight": human_oversight,
        },
        "behavior": {
            "logging_enabled": False,
            "log_format": "none",
            "max_actions_per_minute": 0,
            "kill_switch": True,
            "escalation_policy": "halt-and-notify",
        },
        "metadata": {
            "created_at": now,
            "updated_at": now,
            "tags": ["autogen"],
            "model": fields["model"],
        },
    }

    return card


def attach_card(agent: Any, card: Dict[str, Any]) -> None:
    """Attach a KYA identity card to an AutoGen agent instance.

    Stores the card as agent._kya_card for retrieval by tools and middleware.
    """
    agent._kya_card = card


def get_card(agent: Any) -> Optional[Dict[str, Any]]:
    """Retrieve the KYA card attached to an AutoGen agent, if any."""
    return getattr(agent, "_kya_card", None)
