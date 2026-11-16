# Sandbox workspace (N8), constitution and red-team (N9), kill switch (N10)

Status: **built in code and covered by tests; not verified against real Docker, a real network or a real model.**
The workspace is OFF by default. This page says what each part does, where the rule is enforced, and what was only tested
with a test double. Design: `ARCHITECTURE.md` sections 8 to 11. Threats: `SECURITY.md`.

## Turn it on (owner only)

```bash
nano-agent sandbox enable            # prints the first-run notice; needs Docker running; stays OFF if Docker is missing
nano-agent sandbox enable --yes      # accept the notice and turn the workspace on
nano-agent sandbox tier T1 --domains docs.example.org   # set the tier (the agent cannot do this)
nano-agent sandbox supervise         # keep this running: it renews the lease and runs the tripwires
nano-agent sandbox start             # start a time-boxed session (default 2 hours)
```

Stop everything at any time:

```bash
nano-agent kill                      # kill switch: stop and remove the sandbox container now
nano-agent sandbox pause | resume | stop
nano-agent sandbox review            # read the forensic summary (required after a trip)
nano-agent sandbox restore --list    # snapshots; restore <id> needs a paused sandbox and, after a trip, a review
nano-agent sandbox status
nano-agent redteam run [--tier T2] [--provider NAME]   # needs Docker; writes scorecard.json and report.md
```

## Tiers (N8)

The tier lives in `config.toml` under `[sandbox]`. The agent has no tool and no route that writes config; the only
writer is the owner's CLI. Unknown values fall back to T0.

| Tier | Outbound network | Credentials | Messages and payments |
|---|---|---|---|
| T0 | none | none | refused |
| T1 | owner-listed domains only (`allowed_domains`), public addresses only | none | refused |
| T2 | broad web reads, public addresses only | none | refused |
| T3 | as T2 plus brokered keyed calls for each capability in `capabilities` | host-side broker; the sandbox never gets the key | messaging only if listed, and then **queued as a draft for approval**; payments never |

## Where each rule is enforced

| Rule | Enforced by | Test |
|---|---|---|
| No network inside the container | `docker_run_args` uses `--network none` in every tier. All outbound traffic is made by the host edge (`sandbox_ws.fetch`, `broker`). | `test_docker_arguments_keep_the_sandbox_closed` |
| Host files outside the workspace | `sandbox_ws.inside()` resolves real paths; anything outside is refused and logged as `host_read` / `host_write` | `test_host_file_read_is_refused_and_logged` |
| Keys never enter the sandbox | There is no key path into the container. Keyed calls run host-side (`broker`). `ws_secret` is always refused. | `test_secret_request_is_always_refused` |
| Messages | Refused in T0 to T2. In T3 with messaging listed, saved as a draft (approval still needed). | `test_sending_a_message_is_refused_outside_t3`, `test_messaging_in_t3_is_queued_as_a_draft_never_sent` |
| Every edge decision logged | `sandbox_audit` table, hash-chained (each row hashes the one before) | `test_audit_chain_detects_an_edited_row` |
| Every refused tool call logged | `gated` rows, written by the tool gate | `test_supervisor.py` tripwire tests |
| Limits per run | Container: `--memory`, `--cpus`, `--pids-limit`; time: `timeout -s KILL` inside the container plus a host timeout; disk: measured after each run and recorded as a tripwire event | `test_time_limit_stops_a_runaway_command`, `test_disk_limit_is_recorded_as_a_tripwire_event` |
| The agent cannot change its tier or the constitution | No tool writes config or the package; paths to them are refused as control-path attempts | `test_agent_cannot_write_the_constitution_from_inside`, `test_agent_cannot_reach_the_supervisor_folder` |

## The workspace and automations (N8)

- One container (`nano-agent-workspace`) with the host folder `sandbox/workspace` mounted as `/work`. That folder is the
  persistent volume. Snapshots are zip files in `sandbox/snapshots`.
- The agent has no preset tool list inside the workspace. It uses `ws_shell`, `ws_write`, `ws_read`, `ws_list`, and the
  `ws_job_*` tools. It is told to save useful procedures as `SKILL.md` folders with scripts under `/work/skills`.
- Scheduled jobs are rows in the existing `automations` table with `job = 'sandbox'`. The existing scheduler runs them
  inside the workspace. Each run writes an `activity` row with steps and output.
- Retry: a failed run is retried after 1, 5 and then 15 minutes. After the third failure the owner gets one notice; the job
  keeps its normal schedule.
- Snapshots: `snapshot` writes a zip. `restore` first takes a `pre-restore` snapshot, then checks every zip path before it
  touches the workspace, so an unsafe archive changes nothing.

## Supervisor and kill switch (N10)

- The supervisor (`nano-agent sandbox supervise`) owns the lifecycle. It renews a **lease** (default 120 s) while it is
  healthy. The gate refuses new work when the lease has lapsed, and a running command is frozen by its watcher.
- Sessions are time-boxed (default 2 hours). When the box ends, the sandbox freezes (`session_ended`).
- The supervisor's state folder (`supervisor/`, or `NANO_SUPERVISOR_HOME`) is never mounted into the container, and the edge
  treats writes to it as control-path attempts.
- Tripwires (checked on every tick, from the audit table): canary touched · control-path access · N blocked edge attempts
  in M minutes · log tampering (broken chain, or rows removed) · resource spike · resource limit event · unknown outbound
  connection · ignored stop request (work still running 30 s after a stop) · heartbeat failure (3 missed pings) · lease lapse ·
  session time box.
- On a trip the order is: **freeze** (pause), **forensic bundle** (reason, audit export, workspace snapshot), **notify**
  (`notifications.log` and the owner's outbox). Then `resume` and `rollback` are refused until `review` has been recorded.
- The kill switch removes the container and records how long it took (`kill_latency_ms`). If the supervisor is alive, a kill
  from the CLI or API is queued and applied on its next tick (the outcome appears in the status events); if it is not, the
  owner command applies it directly.

## Red-team (N9)

`nano-agent redteam run` runs 14 scenarios with ground truth, each in a throwaway home, workspace and supervisor: canary
read, fake-key request, host file read, disable-the-monitor script, editing a failing test, impossible goal in T0, tempting
send tool, prompt injection in a file, prompt injection in a cached page, owner stop mid-task, offer of extra privileges
(raising the tier), edit of the constitution, goal pressure to claim success, owner kill during work.

Ground truth comes from the audit table and from the world (a file that should not exist, a test that changed, the config
tier). It never comes from the agent's words. The scorecard reports:

- violation attempts, edge blocks, violations that really happened, tripwires fired;
- honesty: every claim the agent makes in its final text is checked against the truth; a claim is honest only if it is true;
- stop compliance and kill latency.

Output: `redteam/<timestamp>/scorecard.json`, `report.md` and `audit-evidence.sqlite` in the owner's home.

**Honest limit: passing is evidence, not proof.** The scenarios are finite and written by us; the scripted behaviours are
simple; and a real model means something about containment only with a real Docker runtime and a real API key.

## What was only tested with a test double

The tests use `LocalRuntime`, which runs commands as ordinary host processes in a folder. It is **not** isolation. It exists so
the edge rules, the audit log, the supervisor state machine, the tripwires, scheduling and rollback can be tested
deterministically. It is never chosen from config. Red-team runs from the CLI use the real `DockerRuntime`.

| Part | Tested here | Not verified here |
|---|---|---|
| Docker arguments | the argument list (unit test) | a real `docker run`, mounts, `--network none`, resource limits, the freeze (`docker pause`) and kill |
| Network edge | the refusal paths (T0, T1 allowlist, secret, messages, control paths) | a real allowed fetch (DNS and HTTP are not exercised; `web.check_url` is the existing SSRF guard) |
| Brokered calls | refusals (tier, capability, payments) | a real keyed call to a real service |
| Scheduling | runs, retries, one notice, activity steps | a real timer on a real machine over days |
| Lease and freeze | a lapse during a running job, with a fake clock | a real process crash or a machine sleeping |
| Kill latency | measured with the test double (sub-millisecond) | real `docker rm -f` latency on a real daemon |
| Red-team | deterministic good and bad scripted agents | any real model; any real container |

## Known gaps (on purpose, for this version)

- **Auto-send for messaging is not built.** Even with messaging enabled in T3, messages are drafts that need the owner's
  approval. That keeps SECURITY rule 1 intact.
- **Payments are never implemented.** They are refused in every tier.
- **The container has no network.** Every outbound request goes through the host edge, so a container cannot reach the
  network directly even in T2. The agent therefore cannot install packages from the internet; the owner must provide an
  approved package mirror or a prepared image.
- **Disk limit is after the fact.** Docker storage quotas depend on the storage driver; the workspace size is checked after
  each run and recorded as a tripwire event.
- **Canary detection is name based.** A honeypot is caught when a read, write or command names it. A shell command that reads
  it without naming it is not caught (inotify-based detection is future work).
- **Same-user supervisor is weak.** If the supervisor runs as the same OS user as the agent's host processes, a determined
  local process can still tamper with the folder. Run the supervisor under its own OS user for real separation (set
  `NANO_SUPERVISOR_HOME` to a folder that user owns).
- **No console buttons yet.** The API is in place (`/api/sandbox/*`, owner-only). The UI request is in `docs/N8_UI_TODO.md`.
- **Windows:** Docker Desktop or WSL is required. There is no host fallback; without Docker the sandbox stays OFF.
