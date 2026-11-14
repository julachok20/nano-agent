"""Known providers: what to show in the wizard and which adapter to use. Model ids are suggestions only; the
user can type any id their provider offers (lists change often)."""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    "openai": {"label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1", "needs_key": True,
               "chat": "gpt-4o", "fast": "gpt-4o-mini", "key_url": "https://platform.openai.com/api-keys"},
    "anthropic": {"label": "Anthropic (Claude)", "kind": "anthropic", "base_url": "https://api.anthropic.com/v1", "needs_key": True,
                  "chat": "claude-sonnet-5-5", "fast": "claude-haiku-5-5", "key_url": "https://console.anthropic.com/settings/keys"},
    "gemini": {"label": "Google Gemini", "kind": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "needs_key": True,
               "chat": "gemini-2.5-flash", "fast": "gemini-2.5-flash", "key_url": "https://aistudio.google.com/apikey"},
    "openrouter": {"label": "OpenRouter (many models, one key)", "kind": "openai", "base_url": "https://openrouter.ai/api/v1", "needs_key": True,
                   "chat": "openai/gpt-4o", "fast": "openai/gpt-4o-mini", "key_url": "https://openrouter.ai/keys"},
    "groq": {"label": "Groq", "kind": "openai", "base_url": "https://api.groq.com/openai/v1", "needs_key": True,
             "chat": "llama-3.3-70b-versatile", "fast": "llama-3.1-8b-instant", "key_url": "https://console.groq.com/keys"},
    "together": {"label": "Together AI", "kind": "openai", "base_url": "https://api.together.xyz/v1", "needs_key": True,
                 "chat": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "fast": "meta-llama/Llama-3.2-3B-Instruct-Turbo", "key_url": "https://api.together.ai/settings/api-keys"},
    "deepseek": {"label": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com/v1", "needs_key": True,
                 "chat": "deepseek-chat", "fast": "deepseek-chat", "key_url": "https://platform.deepseek.com/api_keys"},
    "ollama": {"label": "Ollama (local, native API)", "kind": "ollama", "base_url": "http://localhost:11434", "needs_key": False,
               "chat": "llama3.1", "fast": "llama3.2", "key_url": ""},
    "lmstudio": {"label": "LM Studio (local)", "kind": "openai", "base_url": "http://localhost:1234/v1", "needs_key": False,
                 "chat": "", "fast": "", "key_url": ""},
    "vllm": {"label": "vLLM or any local OpenAI-compatible server", "kind": "openai", "base_url": "http://localhost:8000/v1", "needs_key": False,
             "chat": "", "fast": "", "key_url": ""},
    "custom": {"label": "Custom OpenAI-compatible base URL", "kind": "openai", "base_url": "", "needs_key": False,
               "chat": "", "fast": "", "key_url": ""},
    "fake": {"label": "Fake model (no network, for trying the console and tests)", "kind": "fake", "base_url": "fake://", "needs_key": False,
             "chat": "fake-1", "fast": "fake-1", "key_url": ""},
}

ORDER = ["openai", "anthropic", "gemini", "openrouter", "groq", "together", "deepseek", "ollama", "lmstudio", "vllm", "custom", "fake"]
