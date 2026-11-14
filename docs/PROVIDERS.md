# Model providers

nano Agent has adapters for OpenAI-compatible APIs, Anthropic Messages, Google Gemini and native Ollama. A fake provider is available for setup checks and tests; it does not make real model calls.

The setup wizard selects a provider and its model. OpenAI-compatible endpoints cover hosted services and local servers such as vLLM, LM Studio and Ollama's `/v1` interface. For a local endpoint, use its local base URL and keep the model service bound to localhost or another private network.

Provider keys are stored in the secret store, separately from `config.toml`. Do not put them in command-line arguments, repository files, screenshots, logs or chat messages. Optional `fast` and `vision` roles fall back to the chat model when unset.

Use `nano-agent models list`, `nano-agent models add`, `nano-agent models set-key`, `nano-agent models use` and `nano-agent models test` for model management. Exact prompts are shown by `nano-agent models --help` and the setup wizard.

Live calls require the provider's own account and credentials. CI uses fake responses and does not prove a hosted provider account works.
