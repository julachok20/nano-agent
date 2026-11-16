# UI request for the console (for the dashboard owner)

The owner-only API for the sandbox workspace is built (`src/nanoagent/gateway/sandbox_api.py`). The console files
(`gateway/console.py`, `gateway/static/console.js`) were not touched on purpose, so this is the request for them.
Every route needs the owner's session, like the rest of `/api`.

## Routes

| Method | Path | What it does |
|---|---|---|
| GET | `/api/sandbox/status` | config (workspace on/off, tier, allowed domains, capability names, snapshots), supervisor state, lease and session times, trip reason, reviewed flag, last 20 events, audit chain OK |
| GET | `/api/sandbox/audit?limit=200` | last audit rows: time, kind, target, decision, reason, run id |
| POST | `/api/sandbox/start` | start a time-boxed session (only from idle, session ended, or killed) |
| POST | `/api/sandbox/pause` | freeze now, keep the container |
| POST | `/api/sandbox/resume` | continue (refused after a trip until reviewed) |
| POST | `/api/sandbox/stop` | ask the agent to stop; running work is watched for 30 s |
| POST | `/api/sandbox/kill` | kill switch: remove the container now |
| POST | `/api/sandbox/review` | record that the forensic log was read |
| POST | `/api/sandbox/rollback` | JSON body `{"snapshot": "<id>"}`; needs a paused sandbox and, after a trip, a review |

Every POST returns `{"ok": ..., "error": ...}` or `{"ok": true, "queued": true}` when the supervisor is running and applies the
command on its next tick. Refusals made on that tick are written to `events` on the status route.

## Panel to build

1. **Status card:** a clear label for each state (idle, running, paused, stop requested, session ended, frozen for review,
   killed), the tier, the allowed domains, and time left in the session.
2. **Big buttons:** Kill (always visible, red, one tap, no confirm), Stop, Pause/Resume. Start only when idle or killed.
3. **Trip banner:** when `trip` is set, show the reason, a Review button, and then Resume or Rollback (rollback lists snapshot
   ids from `status.config.snapshots`).
4. **Audit list:** newest first, with decision colour (allow, deny, trip, queued). Show `target` as plain text only (the console
   already renders with `textContent`; keep it that way).
5. **First-run notice:** show the `sandbox.notice` string (en and th) before the owner can turn the workspace on. Turning it on
   is a CLI action (`nano-agent sandbox enable --yes`), not a route; the panel only shows the state.

## Rules for the UI

- Do not show keys, tokens or tier-changing controls for the agent. The tier is set in the CLI only.
- Do not add a route that changes the tier or the constitution.
- Strings go through the i18n layer (en and th keys together).
