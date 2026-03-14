# autogen-kya

KYA (Know Your Agent) identity verification for Microsoft AutoGen agents.

## Install

```bash
pip install autogen-kya
```

## Quick Start

```python
from autogen_kya import KYAAgent

agent = KYAAgent(
    name="my-agent",
    version="1.0.0",
    capabilities=["coding", "analysis"]
)

card = agent.identity_card()
print(card)
```

## What is KYA?

Know Your Agent (KYA) is an identity standard for AI agents. It provides unique agent identity with Ed25519 signing, framework-native integration, and verifiable credentials.

See [kya-agent](https://github.com/LuciferForge/KYA) for the core library.

## Related

- [kya-agent](https://github.com/LuciferForge/KYA) — Core library
- [crewai-kya](https://github.com/LuciferForge/crewai-kya) — CrewAI
- [langchain-kya](https://github.com/LuciferForge/langchain-kya) — LangChain
- [llamaindex-kya](https://github.com/LuciferForge/llamaindex-kya) — LlamaIndex
- [dspy-kya](https://github.com/LuciferForge/dspy-kya) — DSPy
- [smolagents-kya](https://github.com/LuciferForge/smolagents-kya) — smolagents

## License

MIT
