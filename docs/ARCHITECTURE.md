# nano Agent: architecture and extraction plan

nano Agent is the open-source, provider-agnostic cousin of a private personal assistant that ran on a
home server behind a LINE Official Account. This note records what was kept, what was left out, and why
the agent loop is now our own.

## 1. Goals

1. One install command, one setup wizard, any AI model by API key (or a local server by base URL).
2. A private web console (dashboard, chat, memory, skills, learning, activity) that only the owner can open.
3. An optional LINE connector (official Messaging API only).
4. Safety rules that are code, not prompts: approval before anything is sent, owner-only routes,
   a hard denylist for self-modification patches, secrets never printed or logged.
5. Small enough to read in an afternoon: plain Python, SQLite, FastAPI, httpx, no heavy framework.

## 2. The agent loop (decision)

The private project used the external Hermes Agent as the brain (`hermes -z`, MCP tools, Hermes cron).
nano Agent does **not** depend on it.

| Option | Verdict |
|---|---|
| Keep Hermes as the brain | Forces every user to install and configure a second large project; ties us to its release cycle and its model plumbing; cannot run with only an API key. Rejected as a hard dependency. |
| Adopt a big agent framework (LangChain etc.) | Large dependency surface, fast-moving APIs, more than we need. Rejected. |
| **Own small tool-calling loop (chosen)** | About 150 lines (`agent.py`). Works with every provider through one internal message format. Easy to test with a scripted fake model. Keeps the safety hooks (approval-only tools, untrusted-text marking, step limit) in one place. |

How it works:

```
user text --> Agent.run()
   build system prompt: rules + owner profile + preferences + relevant memory + skill index
   loop (max N steps):
      provider.chat(messages, tools)  --> text and/or tool calls
      for each tool call: registry.call(name, args)  (logged to the activity table)
      tool results go back as DATA, wrapped and labelled untrusted
   final text --> reply
```

The tool registry (`nanoagent/tools/`) is plain Python functions with a decorator. It is reused three ways:
the agent loop, the console API, and an optional **MCP stdio server** (`nano-agent mcp`, extra `[mcp]`), so
Hermes, Claude Desktop or any MCP client can use the same tools. That is the "keep the tool code reusable"
promise: tools never import the loop.

Providers are adapters behind one `Provider.chat()` interface (see `docs/PROVIDERS.md`):
OpenAI-compatible (OpenAI, OpenRouter, Groq, Together, DeepSeek, vLLM, LM Studio, Ollama's `/v1`, any base URL),
Anthropic Messages, Google Gemini, and Ollama native. Roles (`chat`, `fast`, `vision`) map to models.

### Scheduler (replaces Hermes cron)

`nanoagent/scheduler.py` is an asyncio loop inside the gateway process. Jobs live in the `automations` table
(interval, daily at HH:MM, weekly) and call registered job functions: reminders, the daily brief, outbox flush,
database backup, weekly self-review, health check. One process, no cron daemon, works on Linux, macOS, WSL.
The owner can pause, run now and edit schedules in the console. A job that fails is logged to `activity` and
retried at its next slot; it never kills the gateway.

## 3. Extraction plan: what came from the private project

"Ported" means rewritten against the nano Agent data layer, with all personal names, ids, hosts, Thai-only
text and Hermes paths removed; the idea, the schema and the safety design are kept.

| Private module | Fate in v0.1 | Notes |
|---|---|---|
| `gateway.py` (webhook, approvals, LIFF, media, internal routes) | **Ported** to `gateway/` | LINE signature check, one-time-code approvals, owner-only API. No Vercel relay, no Tailscale-Funnel path, no LINE Chrome trigger messages. |
| `liff_page.py` (console) | **Ported** to `gateway/console.py` + `static/console.js` | Same hubs and look; text through the i18n layer (English, Thai). |
| `mcp_server.py` (tools) | **Ported** to `tools/` registry | Same tool ideas (memory, tasks, reminders, drafts, skills, dashboard read, code sandbox); Google tools optional. |
| `skills.py` | **Ported** to `skills.py` | Hermes `SKILL.md` format kept so skills import both ways. Imports stay quarantined until the owner reviews and enables. |
| `learning.py`, `review.py` | **Ported** to `learning.py` | Bounded preference schema, "what I learned" log with undo, weekly self-review job. |
| `usermodel.py` | **Ported** (reduced) to `usermodel.py` | Traits with evidence records, confidence threshold, owner correction wins, delete = forget. Never stores chat text. |
| `offers.py` | **Deferred to v0.2** | Proactive offers need the calendar and events layer; listed in the roadmap. |
| `buddy.py`, `companion.py` | **Ported** (reduced) to `companion.py` | Opener templates filled from stored facts (no model call), relationship level with undo, honesty rule, tap-to-talk orb in the console. |
| `activity.py` | **Ported** to `activity.py` | Background-work visibility: tracked tasks, steps, live pill. |
| `patch_policy.py`, `patcher.py` | **Ported** to `patching.py` | Hard denylist in code, enforced at proposal and apply time, tests before and after, owner approval, automatic rollback. Denylist rewritten for the nano tree. |
| `sandbox.py` | **Ported, optional** | Runs code in a no-network Docker container. Disabled unless Docker is present and enabled in config. |
| `tools/stt`, `tools/tts` | **Ported as adapters, optional** | `voice/` has a Whisper-compatible STT client and an OpenAI-compatible TTS client; browser speech is the default. |
| `drafter.py`, `drafts.py` | **Ported** to `drafts.py` | Drafting model call has no tools. Drafts need approval. |
| `memory.py`, `cards.py` | **Ported** (reduced) to `memory.py`, `db.py` | Facts, rules, tasks, outbox; the six-type memory is reduced to facts and rules in v0.1. |
| `health.py`, backup scripts | **Ported** to `health.py` and scheduler jobs | Generic: disk, DB integrity, provider ping; nightly backup with restore check. |
| `dashboard.py` | **Ported** (reduced) | System page is generic: CPU/RAM/disk through optional `psutil`; GPU shown only when `nvidia-smi` exists; no Docker or service names. |
| `line_web.py`, `line_chats.py`, `line_export.py`, `flush_outbox.py` trigger | **Left out** | Drive the owner's personal LINE through a Chrome extension. Personal, fragile, not an official API. |
| `media_fwd.py`, `timetable.py`, `vision.py` (timetable use), `imgcrop.py` | **Left out** | School timetable and personal media flows. Vision remains as an optional model role. |
| `executive.py`, `planner.py`, `calview.py`, `projects.py`, `newspaper`, `myreport`, `daily_plan` | **Left out of v0.1** | Owner-specific planning; calendar page returns with Google in v0.2. A generic daily brief ships instead. |
| `research.py`, `sources/news.py` | **Ported as simple tools** | `web_search` and `web_fetch` (SSRF-guarded). |
| `sources/google_*` | **Optional extra `[google]`** | Calendar read plus event create and Gmail **drafts only**. Never sends mail. |
| `team.py` and the owner's separate multi-agent and social-posting apps | **Left out** | Other projects, not part of nano Agent. Roadmap: a team bridge. |
| `relay/` (a hosted webhook relay), `systemd/`, `deploy/`, GPU-box Dockerfiles | **Left out** | Specific to one machine and host. nano Agent can print its own systemd user unit on request. |
| personal handover notes, roadmap, fixtures with real names, style files | **Left out** | Personal data. All test data in nano Agent is synthetic. |

Not copied at all: `.git` history, databases, memory, chats, tokens, `.env`, `credentials.json`, backups,
`*.bak-*` files, the model-server key handling of the original machine, the school timetable. See `SECURITY.md`.

## 4. Package layout

```
src/nanoagent/
  cli.py wizard.py doctor.py config.py secrets.py paths.py i18n.py
  providers/    base, openai_compat, anthropic, gemini, ollama, fake, presets
  tools/        registry, core, web, google (optional), sandbox (optional)
  agent.py scheduler.py db.py activity.py memory.py drafts.py skills.py
  learning.py usermodel.py companion.py patching.py health.py
  gateway/      app (FastAPI), auth, line (connector), console (HTML), static/
  voice/        stt, tts adapters
tests/          synthetic data only; a fake provider drives the agent
scripts/        secrets_scan.py, preview_console.py, e2e_check.py
```

## 5. Data layout (`~/.nano-agent`, override with `NANO_AGENT_HOME`)

```
config.toml       non-secret settings
secrets.toml      API keys, LINE secrets, owner token (mode 0600; or the OS keyring)
data/nano.db      SQLite: memory, tasks, drafts, outbox, activity, preferences, traits, automations
data/skills/      SKILL.md folders (active), skills-pending/ (quarantine), skills-trash/
data/backups/     nightly copies (kept 14 days)
logs/             gateway.log (secrets masked)
```

## 6. Request flows

**Console.** The CLI opens `/console` with the owner token in a URL fragment, which is not sent to the server.
The page exchanges it once for an HttpOnly same-site cookie, then removes the fragment. The HTML shell and static
assets are public but contain no owner data; private `/api/*` routes require the owner credential. A test enumerates
registered routes and fails if a private route is reachable without it.

**LINE (optional).** LINE posts to `/webhook/line`. The body is verified with HMAC-SHA256 over the raw bytes
and the channel secret before anything is parsed. Only the configured owner user id is served; all other
senders get no reply. Replies use the reply token (free); pushes are queued in the outbox and only sent for
approved items, urgent reminders and the brief.

**Approval.** The agent can only call `prepare_message`, which writes a draft and shows a card. The draft has
a random one-time code. Sending needs the owner's tap (LINE button with the code, or the console button).
There is no direct-send path in v0.1. See `SECURITY.md`.

**Self-modification.** The agent may call `propose_patch` for its own plugin code area. `patching.py` applies
the hard denylist, runs tests on a copy, shows the diff to the owner, and applies only after approval, with
rollback. Core safety files are on the denylist and cannot be patched by the agent.

## 7. What is deliberately not here

- No auto-reply to other people, no direct send, no auto-approval.
- No telemetry of any kind. Nothing leaves the machine except calls to the AI provider you configured, the
  LINE API if you enable it, and web fetches you or the agent request.
- No reading of private chats through a browser extension.
