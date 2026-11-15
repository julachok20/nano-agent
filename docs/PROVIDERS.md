# Model providers

nano Agent has adapters for OpenAI-compatible APIs, Anthropic Messages, Google Gemini and native Ollama. A fake provider is available for setup checks and tests; it does not make real model calls.

The setup wizard selects a provider and its model. OpenAI-compatible endpoints cover hosted services and local servers such as vLLM, LM Studio and Ollama's `/v1` interface. For a local endpoint, use its local base URL and keep the model service bound to localhost or another private network.

Provider keys are stored in the secret store, separately from `config.toml`. Do not put them in command-line arguments, repository files, screenshots, logs or chat messages. Optional `fast` and `vision` roles fall back to the chat model when unset.

Use `nano-agent models list`, `nano-agent models add`, `nano-agent models set-key`, `nano-agent models use` and `nano-agent models test` for model management. Exact prompts are shown by `nano-agent models --help` and the setup wizard.

Live calls require the provider's own account and credentials. CI uses fake responses and does not prove a hosted provider account works.

## Choosing a provider

Use the setup wizard for the first model. Hosted adapters send the prompt and selected context to that service. A local Ollama or OpenAI-compatible server can keep inference on your machine, depending on how that server is configured. For local OpenAI-compatible servers, enter the server's `/v1` base URL and the model identifier it exposes.

```bash
nano-agent models list
nano-agent models add openai-compatible --name local --base-url http://127.0.0.1:1234/v1 --model my-model
nano-agent models use chat local/my-model
nano-agent models test
```

Replace the sample URL and model with the values from your server. Use `nano-agent models add --help` for the provider names and options supported by the installed version. A hosted provider usually needs a key; `nano-agent models set-key NAME` prompts privately, while `--api-key-stdin` and `--api-key-env VAR` support noninteractive setup.

## Troubleshooting

Run `nano-agent doctor --offline` first to check local configuration, then `nano-agent models test` to make one live request. A connection error usually means the server URL or network path is wrong. An authentication error points to the key; a model error points to its identifier or account access. The `fast` and `vision` roles are optional and use the chat role if unset. Never paste a key or token into a bug report; redact URLs containing credentials.

`nano-agent models list` should show the configured provider and the `chat` role. A successful `models test` reports the model and a completed response; the fake provider returns a synthetic response without network access. If a local server test fails, first confirm that its `/v1` endpoint and chosen model are available from the same machine. Hosted calls and billing are controlled by the provider account, not by nano Agent.
