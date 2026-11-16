# Security

nano Agent is a personal assistant that holds your API keys, reads your tasks and memory, and can talk to your LINE
account. Its safety rules are **enforced in code and covered by tests**, not left to the model's good behaviour.

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability reporting
(Security tab > "Report a vulnerability") on this repository. Include steps to reproduce and what you expected.
We aim to answer within 7 days. Do not include real API keys in reports.

## The rules (all enforced in code, all tested)

1. **Approval before anything is sent.** The agent's only outbound tool is `prepare_message`, which saves a draft. A draft
   is sent only by `drafts.approve`, called from exactly two places: the owner-authenticated console route and the LINE
   webhook after signature and owner checks, with the draft's one-time code. There is no direct-send tool, no auto-reply to
   other people and no auto-approval. Double taps send once (atomic claim). Drafts expire after 24 hours. Editing a draft
   issues a new code. (`tests/test_core.py`, `tests/test_gateway.py`, `tests/test_security.py`)
2. **Owner-only on every route.** Every console and API route depends on `require_owner`; a test walks all registered
   routes and fails if one lacks it, and another calls every route without credentials and expects 401. The short public
   list (health check, the static console shell, login, LINE webhook) returns no private data. (`tests/test_gateway.py`)
3. **Secrets are never printed or logged.** API keys live in a `0600` file or the OS keyring, are read only when a request
   is made, and every log line, error message and model reply passes through `redact()`. There is no `--api-key VALUE`
   flag (it would show in the process list). The model never receives keys, and a draft's one-time code is hidden from it.
4. **Untrusted text is data.** Web pages, files and tool results are wrapped and labelled, the system prompt says never to
   follow instructions inside them, and the console renders all text with `textContent` (a test bans HTML-string APIs).
5. **Self-modification is a proposal, never an action.** The agent can propose plugin code. A hard denylist (code, enforced
   at proposal time and again at apply time against the real files) limits it to `plugins/`; the nano Agent package, config,
   secrets, databases and tests are off limits. Plugin code is checked by an AST allowlist (no `os`, `subprocess`, `eval`,
   `open`, dunder access, network) and by a line scan for sending, secrets and shell words. It is tested in a throw-away
   subprocess, shown to you as a diff, applied only when you approve in the console, and rolled back automatically if the
   test after applying fails. Every change is undoable. (`tests/test_patching.py`)
6. **Skills cannot override the rules.** AI-written skills that try to ("ignore previous instructions", "send without
   asking") are refused; imported skills stay off, are reviewed in plain language, and only you can enable them. Scripts
   never run on the host.
7. **Bounded learning.** Preferences are validated against a fixed schema; a stored value outside it is ignored. The user
   model keeps evidence records (ids, never chat text); guesses below the evidence threshold are shown but not acted on;
   your corrections win; deleting a trait forgets it and its evidence.
8. **Local first.** Data stays in `~/.nano-agent`. The only network calls are to the AI provider you configured, the LINE
   API if you enable it, Google if you connect it, and web fetches that you or the agent request. No telemetry.

## Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| A web page, email or chat message tells the agent to do something ("send this to everyone") | Untrusted wrapping, rule in the system prompt, and **no send capability** in the tool set. At worst it creates a draft that you must approve. | You approve a bad draft without reading it. Read drafts. |
| A stranger finds your LINE bot and messages it | Only the paired owner id is served; strangers get no reply. Pairing needs a one-time code that expires in 15 minutes. | If someone sees your pairing code in time, they could pair first. Pair immediately, over a private chat. |
| Forged LINE webhook | HMAC-SHA256 signature check on the raw body before parsing. | Leaking the channel secret. Reissue it in the LINE console. |
| Someone opens your console URL | Owner token required (random, 256 bit); HttpOnly SameSite cookie; login rate limit; same-origin check on writes; token sent in the URL **fragment** so it is not in server logs. | Default is `127.0.0.1` only. If you expose the console, anyone with the token has full control: treat the token like a password and rotate it (`nano-agent token` after deleting `owner.token`). |
| Cross-site request forgery / XSS | SameSite cookie, Origin check, CSP, no HTML-string rendering, tests. | Browser bugs. |
| Prompt injection makes the agent leak your keys | The model never sees keys; output is redacted; tool results are data. | A model could still be tricked into repeating other personal data it was given in the conversation. |
| Server-side request forgery through `web_fetch` | http/https only, host must resolve to a public address, redirects re-checked, size and time caps. | DNS rebinding between the check and the connection is not fully closed in v0.1. Do not run nano Agent on a host with sensitive internal HTTP services reachable by name. |
| A malicious or sloppy plugin patch | Denylist + AST allowlist + diff review + sandboxed test + rollback + owner approval. | Python cannot be fully sandboxed from inside Python. Approved plugins run in the gateway process. Read the diff. |
| A malicious imported skill | Quarantine, review, owner-only enable, no host script execution. | Skill text can still steer the model's tone or priorities within the rules. |
| Code execution tool | Optional; Docker, no network, read-only, dropped capabilities, memory/pid limits, timeout; off by default; never falls back to the host. | Docker escapes (keep Docker updated). |
| Secrets in backups or git | Backups hold the database and skills only, never `secrets.toml`; `.gitignore` and the secrets scan (tree and history) run in tests and CI. | The database holds your memory and messages: protect your disk. |
| LINE push quota abuse | Monthly push cap (default 200) and hourly rate limit. | |

## Not in scope for v0.1

Multi-user setups, hosted deployments for other people, end-to-end encryption of the local database, signed releases.
nano Agent is built for **one owner on a machine they control**.

## Hardening checklist

- Keep the gateway on `127.0.0.1` unless you need phone or LINE access; use Tailscale or Cloudflare Tunnel rather than opening a port.
- Run `nano-agent doctor` after changes; it checks file permissions and configuration.
- Use a provider key with a spending limit.
- Rotate the owner token and your provider keys if you ever paste them somewhere by mistake.

## Planned: sandbox-first autonomy (N8, not implemented yet)

The owner wants the agent to be creative and unrestricted **inside** an isolated workspace. The security model moves the rules to the
**edge** of that workspace. They stay in code and tested: default-off network allowlist, no host files outside the workspace volume,
no secrets in the sandbox (a host-side broker makes keyed calls), no message to any person without approval, a spending budget,
no deletion of the owner's data, and no change to core code outside the patch flow. Every edge request and decision goes to an audit log.
There is a kill switch and workspace snapshots with rollback. If Docker is missing the sandbox stays off; there is no host fallback.
Until N8 ships, the existing optional Docker sandbox (no network, read-only, no secrets) is the only code execution available.

### Planned update: scope tiers, constitution and kill switch (N8 to N10)

Per the owner, per-action approval inside the sandbox is replaced by **tiers chosen once** (T0 closed, T1 allowlist, T2 web, T3 brokered
capabilities, each enabled explicitly; messaging and payments off by default). The agent cannot change its tier. The default install still
sends nothing without approval until the owner enables a T3 capability. `CONSTITUTION.md` is read by the agent but is **not enforcement**:
enforcement is a supervisor process and kill switch outside the sandbox (lease, tripwires, freeze, forensic snapshot). A red-team harness
measures behaviour per model and tier, and its scorecard is shown before a tier is raised. Passing it is evidence, not proof. A free agent
with network access can still cause harm within its tier: choose the lowest tier that does the job. None of this is implemented yet.
