# Configuration and local data

The default data directory is `~/.nano-agent`; set `NANO_AGENT_HOME` before running the CLI to choose another. The config file is `config.toml`, SQLite data is under `data/`, logs are under `logs/`, and secrets are stored separately in `secrets.toml` or the OS keyring when selected. Do not share these files: the database and secrets can contain private information.

The setup wizard is the recommended way to configure the app. `nano-agent config show` redacts secret values; `nano-agent config set` changes supported settings. Keep the gateway at its default `127.0.0.1` binding unless you have deliberately configured and secured a private access path.

Common settings include `general.language` (`en` or `th`), `general.timezone` (an IANA name such as `Asia/Bangkok`), model roles (`chat`, `fast`, `vision`), `gateway.host` and `gateway.port`, optional LINE and Google integration settings, and disabled-by-default sandbox settings. Provider credentials are referenced by name in config; secret values belong in the separate secret store.

The full schema and defaults are defined in `src/nanoagent/config.py`. Prefer the CLI and wizard over hand-editing TOML while the gateway is running.

## Everyday changes

Use `nano-agent config show` to inspect the effective settings; it hides secret values. To change a setting, use its dotted name, for example:

```bash
nano-agent config set general.language th
nano-agent config set general.timezone Asia/Bangkok
nano-agent config set gateway.port 8099
nano-agent doctor --offline
```

`general.language` accepts `en` or `th`. The `models.chat`, `models.fast` and `models.vision` values refer to configured provider/model pairs; use `nano-agent models list` and `nano-agent models use` to manage them. `agent.max_steps` limits a single agent turn, and `sandbox.enabled` starts false. The default gateway host is `127.0.0.1` and port is `8099`.

## Files and recovery

`NANO_AGENT_HOME` changes the location for all local state. Set it **before** setup and keep it consistent when starting or stopping the service. Back up the entire directory while the service is stopped if you want to preserve configuration, memory, skills and logs. Do not commit the directory to Git or upload it to support tickets. If a change causes trouble, use `nano-agent doctor --offline`, review `nano-agent logs`, and restore a known good backup of the data directory.

The app never needs a provider key in a command argument. Use the setup hidden prompt or `nano-agent models set-key NAME --api-key-stdin` / `--api-key-env VAR`. The environment variable method is useful in scripts but still requires you to protect the process environment. See [PROVIDERS.md](PROVIDERS.md).

## Check a change

After changing a setting, run `nano-agent config show` to confirm the effective value, then `nano-agent doctor --offline`. If the service is already running, use `nano-agent stop` followed by `nano-agent start` for settings that affect the listener or integrations. If a value is rejected, run `nano-agent config set --help` and compare it with the schema in `src/nanoagent/config.py`; restore the previous value rather than editing a live data file blindly.
