"""Tests for autogen-kya integration.

Tests work without pyautogen installed by using mock agent classes
that mirror AutoGen's ConversableAgent/AssistantAgent/UserProxyAgent.
"""

import json
import pytest

from autogen_kya.card import create_agent_card, attach_card, get_card
from autogen_kya.identity import kya_verify_identity, _verify_card_data
from autogen_kya.trust_gate import kya_trust_gate
from autogen_kya.middleware import (
    kya_verified,
    kya_groupchat_filter,
    KYAVerificationError,
)


# ── Mock AutoGen agents ──


class ConversableAgent:
    """Mimics autogen.ConversableAgent for testing."""

    def __init__(
        self,
        name: str,
        system_message: str = "",
        llm_config: dict = None,
        description: str = "",
    ):
        self.name = name
        self.system_message = system_message
        self.llm_config = llm_config or {}
        self.description = description
        self._function_map = {}

    def register_function(self, func, name=None):
        fname = name or func.__name__
        self._function_map[fname] = func


class AssistantAgent(ConversableAgent):
    """Mimics autogen.AssistantAgent."""

    pass


class UserProxyAgent(ConversableAgent):
    """Mimics autogen.UserProxyAgent."""

    pass


# ── Card creation ──


class TestCreateAgentCard:
    def test_basic_card(self):
        agent = ConversableAgent(
            name="researcher",
            system_message="You are a research assistant.",
            description="Researches topics and summarizes findings.",
        )
        card = create_agent_card(agent, owner_name="TestOrg", owner_contact="test@test.com")

        assert card["kya_version"] == "0.1"
        assert card["agent_id"] == "autogen/researcher"
        assert card["name"] == "researcher"
        assert "research" in card["purpose"].lower()
        assert card["owner"]["name"] == "TestOrg"
        assert card["owner"]["contact"] == "test@test.com"
        assert card["metadata"]["tags"] == ["autogen"]

    def test_card_with_llm_config(self):
        agent = ConversableAgent(
            name="coder",
            system_message="You write Python code.",
            llm_config={"config_list": [{"model": "gpt-4", "api_key": "fake"}]},
            description="A coding assistant agent.",
        )
        card = create_agent_card(agent)
        assert card["metadata"]["model"] == "gpt-4"

    def test_card_with_registered_functions(self):
        agent = ConversableAgent(name="tool_user", description="Uses tools to help.")

        def search_web(query: str) -> str:
            """Search the web for information."""
            return f"Results for {query}"

        def read_file(path: str) -> str:
            """Read a file from disk."""
            return ""

        agent.register_function(search_web)
        agent.register_function(read_file)

        card = create_agent_card(agent)
        declared = card["capabilities"]["declared"]
        assert len(declared) == 2
        names = {c["name"] for c in declared}
        assert "search_web" in names
        assert "read_file" in names

    def test_card_custom_prefix(self):
        agent = ConversableAgent(name="writer")
        card = create_agent_card(agent, agent_id_prefix="myorg")
        assert card["agent_id"] == "myorg/writer"

    def test_card_slug_sanitization(self):
        agent = ConversableAgent(name="Senior Data Analyst!!!")
        card = create_agent_card(agent)
        slug = card["agent_id"].split("/")[1]
        assert "!" not in slug
        assert slug == "senior-data-analyst"

    def test_purpose_minimum_length(self):
        agent = ConversableAgent(name="X", description="Do")
        card = create_agent_card(agent)
        assert len(card["purpose"]) >= 10

    def test_card_has_metadata_timestamps(self):
        agent = ConversableAgent(name="bot")
        card = create_agent_card(agent)
        assert card["metadata"]["created_at"] != ""
        assert card["metadata"]["updated_at"] != ""

    def test_assistant_agent(self):
        agent = AssistantAgent(
            name="assistant",
            system_message="You help with tasks.",
            description="A helpful assistant.",
        )
        card = create_agent_card(agent)
        assert card["agent_id"] == "autogen/assistant"
        assert "helpful" in card["purpose"].lower()

    def test_user_proxy_agent(self):
        agent = UserProxyAgent(name="user_proxy", description="Represents the user.")
        card = create_agent_card(agent)
        assert card["agent_id"] == "autogen/user-proxy"

    def test_system_message_as_list(self):
        agent = ConversableAgent(
            name="chat_agent",
            system_message=[
                {"role": "system", "content": "You are helpful."},
                {"role": "system", "content": "Be concise."},
            ],
            description="A chat agent.",
        )
        card = create_agent_card(agent)
        assert "helpful" in card["purpose"].lower() or "chat" in card["purpose"].lower()


# ── Card attachment ──


class TestAttachCard:
    def test_attach_and_get(self):
        agent = ConversableAgent(name="test")
        card = {"kya_version": "0.1", "agent_id": "test/test"}
        attach_card(agent, card)
        assert get_card(agent) == card

    def test_get_card_none_when_not_attached(self):
        agent = ConversableAgent(name="test")
        assert get_card(agent) is None


# ── Identity verification ──


VALID_CARD = {
    "kya_version": "0.1",
    "agent_id": "autogen/researcher",
    "name": "researcher",
    "version": "0.1.0",
    "purpose": "An AutoGen agent that researches topics and summarizes findings.",
    "agent_type": "autonomous",
    "owner": {"name": "TestOrg", "contact": "test@test.com"},
    "capabilities": {
        "declared": [
            {"name": "web_search", "risk_level": "medium"},
            {"name": "summarize", "risk_level": "low"},
        ],
        "denied": [],
    },
}

MINIMAL_CARD = {
    "kya_version": "0.1",
    "agent_id": "autogen/minimal",
    "name": "minimal",
    "version": "0.1.0",
    "purpose": "A minimal test agent for validation.",
    "owner": {"name": "Test", "contact": "test@test.com"},
    "capabilities": {"declared": [{"name": "test", "risk_level": "low"}]},
}

INVALID_CARD = {
    "kya_version": "0.1",
    "name": "broken",
    # Missing agent_id, purpose, capabilities, owner
}


class TestIdentityVerification:
    def test_valid_card(self):
        result = kya_verify_identity(json.dumps(VALID_CARD))
        assert "VERIFIED" in result
        assert "researcher" in result

    def test_invalid_card(self):
        result = kya_verify_identity(json.dumps(INVALID_CARD))
        assert "FAILED" in result

    def test_invalid_json(self):
        result = kya_verify_identity("not json")
        assert "FAILED" in result
        assert "Invalid JSON" in result

    def test_verify_data_returns_capabilities(self):
        result = _verify_card_data(VALID_CARD)
        assert "web_search" in result["capabilities"]
        assert "summarize" in result["capabilities"]

    def test_verify_data_score(self):
        result = _verify_card_data(VALID_CARD)
        assert result["completeness_score"] > 0


# ── Trust gate ──


class TestTrustGate:
    def test_passes_valid_card(self):
        result = kya_trust_gate(json.dumps(VALID_CARD), min_score=0)
        assert "PASSED" in result

    def test_blocks_low_score(self):
        result = kya_trust_gate(json.dumps(MINIMAL_CARD), min_score=100)
        assert "BLOCKED" in result
        assert "below threshold" in result

    def test_blocks_missing_capabilities(self):
        result = kya_trust_gate(
            json.dumps(VALID_CARD),
            min_score=0,
            required_capabilities="web_search,secret_power",
        )
        assert "BLOCKED" in result
        assert "secret_power" in result

    def test_blocks_unsigned_when_signature_required(self):
        result = kya_trust_gate(
            json.dumps(VALID_CARD),
            min_score=0,
            require_signature=True,
        )
        assert "BLOCKED" in result
        assert "unsigned" in result.lower()

    def test_invalid_json(self):
        result = kya_trust_gate("bad json")
        assert "BLOCKED" in result


# ── Middleware decorator ──


class TestKYAVerified:
    def test_passes_with_valid_card(self):
        agent = ConversableAgent(
            name="good_agent",
            system_message="You are a reliable agent that does good work.",
            description="A trustworthy agent for testing verification.",
        )
        card = create_agent_card(agent, owner_name="Test", owner_contact="t@t.com")
        attach_card(agent, card)

        @kya_verified(min_score=0)
        def task(agent):
            return "executed"

        assert task(agent) == "executed"

    def test_raises_without_card(self):
        agent = ConversableAgent(name="naked_agent", system_message="No card.")

        @kya_verified()
        def task(agent):
            return "executed"

        with pytest.raises(KYAVerificationError, match="No KYA card"):
            task(agent)

    def test_raises_on_low_score(self):
        agent = ConversableAgent(name="weak_agent", system_message="Weak.")
        card = create_agent_card(agent, owner_name="T", owner_contact="t@t.com")
        attach_card(agent, card)

        @kya_verified(min_score=100)
        def task(agent):
            return "executed"

        with pytest.raises(KYAVerificationError, match="below required"):
            task(agent)

    def test_skip_on_fail(self):
        agent = ConversableAgent(name="skippable", system_message="Skip me.")

        @kya_verified(on_fail="skip")
        def task(agent):
            return "executed"

        assert task(agent) is None

    def test_log_on_fail(self, capsys):
        agent = ConversableAgent(name="logged_agent", system_message="Log me.")

        @kya_verified(on_fail="log")
        def task(agent):
            return "executed"

        result = task(agent)
        assert result == "executed"
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_agent_as_kwarg(self):
        agent = ConversableAgent(
            name="kwarg_agent",
            system_message="Test keyword argument passing for verification.",
            description="Agent passed as keyword argument.",
        )
        card = create_agent_card(agent, owner_name="T", owner_contact="t@t.com")
        attach_card(agent, card)

        @kya_verified(min_score=0)
        def task(data, agent=None):
            return f"processed {data}"

        assert task("stuff", agent=agent) == "processed stuff"

    def test_required_capabilities(self):
        agent = ConversableAgent(
            name="tool_agent",
            description="Has registered tools for testing capability checks.",
        )

        def reading():
            """Read data."""
            pass

        agent.register_function(reading)
        card = create_agent_card(agent, owner_name="T", owner_contact="t@t.com")
        attach_card(agent, card)

        @kya_verified(required_capabilities=["reading"])
        def task(agent):
            return "executed"

        assert task(agent) == "executed"

    def test_missing_required_capabilities(self):
        agent = ConversableAgent(
            name="no_tools_agent",
            description="Has no tools at all for testing missing capabilities.",
        )
        card = create_agent_card(agent, owner_name="T", owner_contact="t@t.com")
        attach_card(agent, card)

        @kya_verified(required_capabilities=["admin_access"])
        def task(agent):
            return "executed"

        with pytest.raises(KYAVerificationError, match="Missing capabilities"):
            task(agent)


# ── GroupChat filter ──


class TestGroupChatFilter:
    def test_filters_unverified_agents(self):
        good = ConversableAgent(
            name="verified",
            description="A verified agent with a proper identity card.",
        )
        bad = ConversableAgent(name="unverified", description="No card.")

        card = create_agent_card(good, owner_name="T", owner_contact="t@t.com")
        attach_card(good, card)

        result = kya_groupchat_filter([good, bad])
        assert len(result) == 1
        assert result[0].name == "verified"

    def test_allows_all_when_card_not_required(self):
        a = ConversableAgent(name="a", description="Agent A.")
        b = ConversableAgent(name="b", description="Agent B.")
        result = kya_groupchat_filter([a, b], require_card=False)
        assert len(result) == 2

    def test_filters_by_min_score(self):
        agent = ConversableAgent(
            name="scored",
            description="An agent that has a card but might not meet score threshold.",
        )
        card = create_agent_card(agent, owner_name="T", owner_contact="t@t.com")
        attach_card(agent, card)

        # Score 100 is unlikely to be met by a minimal card
        result = kya_groupchat_filter([agent], min_score=100)
        assert len(result) == 0

        # Score 0 should pass
        result = kya_groupchat_filter([agent], min_score=0)
        assert len(result) == 1
