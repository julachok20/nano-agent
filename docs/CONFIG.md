# Configuration and local data

The default data directory is `~/.nano-agent`; set `NANO_AGENT_HOME` before running the CLI to choose another. The config file is `config.toml`, SQLite data is under `data/`, logs are under `logs/`, and secrets are stored separately in `secrets.toml` or the OS keyring when selected. Do not share these files: the database and secrets can contain private information.

The setup wizard is the recommended way to configure the app. `nano-agent config show` redacts secret values; `nano-agent config set` changes supported settings. Keep the gateway at its default `127.0.0.1` binding unless you have deliberately configured and secured a private access path.

Common settings include `general.language` (`en` or `th`), `general.timezone` (an IANA name such as `Asia/Bangkok`), model roles (`chat`, `fast`, `vision`), `gateway.host` and `gateway.port`, optional LINE and Google integration settings, and disabled-by-default sandbox settings. Provider credentials are referenced by name in config; secret values belong in the separate secret store.

The full schema and defaults are defined in `src/nanoagent/config.py`. Prefer the CLI and wizard over hand-editing TOML while the gateway is running.
