"""Provider layer: build a provider from config + secrets, and pick the right one for a role."""
from __future__ import annotations

from .. import config
from .. import keystore as secrets
from .anthropic import AnthropicProvider
from .base import Provider, ProviderError, Response, ToolCall
from .fake import FakeProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

KINDS = {"openai": OpenAICompatProvider, "anthropic": AnthropicProvider, "gemini": GeminiProvider,
         "ollama": OllamaProvider, "fake": FakeProvider}

_FAKE_SINGLETONS: dict[str, FakeProvider] = {}

__all__ = ["Provider", "ProviderError", "Response", "ToolCall", "make_provider", "for_role", "KINDS"]


def make_provider(cfg: dict, name: str) -> Provider:
    spec = (cfg.get("providers") or {}).get(name)
    if not spec:
        raise ProviderError(f"No provider named '{name}' is configured.", "Run `nano-agent setup` or `nano-agent models add`.")
    kind = spec.get("kind", "openai")
    cls = KINDS.get(kind)
    if not cls:
        raise ProviderError(f"Unknown provider kind '{kind}'.", "Use one of: " + ", ".join(KINDS))
    if kind == "fake":
        return _FAKE_SINGLETONS.setdefault(name, FakeProvider(name))
    key = secrets.get(spec.get("key_ref") or f"provider.{name}") or ""
    return cls(name, spec.get("base_url", ""), key)


def for_role(cfg: dict, role: str = "chat") -> tuple[Provider, str]:
    pname, model = config.model_for(cfg, role)
    if not pname or not model:
        raise ProviderError("No model is configured for this role.", "Run `nano-agent setup` to choose a provider and model.")
    return make_provider(cfg, pname), model
