"""autogen-kya — KYA (Know Your Agent) identity verification for AutoGen agents.

Provides tools, decorators, and helpers to bring cryptographic agent identity
to Microsoft AutoGen workflows. No blockchain, no cloud dependency — just Ed25519 signatures.

Usage:
    from autogen_kya import kya_verify_identity, kya_trust_gate, create_agent_card, attach_card
"""

__version__ = "0.1.0"

from autogen_kya.card import create_agent_card, attach_card, get_card
from autogen_kya.identity import kya_verify_identity
from autogen_kya.trust_gate import kya_trust_gate
from autogen_kya.middleware import kya_verified, KYAVerificationError

__all__ = [
    "kya_verify_identity",
    "kya_trust_gate",
    "kya_verified",
    "KYAVerificationError",
    "create_agent_card",
    "attach_card",
    "get_card",
]
