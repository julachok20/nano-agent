# Install nano Agent

nano Agent supports Linux, macOS and WSL with Python 3.11 or newer. Native Windows is not supported in this preview; use Ubuntu under WSL. The installer does not require sudo and does not edit shell startup files.

## Installer

Download and inspect the script, then run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/julachok20/nano-agent/main/install.sh # scan:allow
less install.sh
bash install.sh
```

The script prints its plan before installing. It prefers `uv`, then `pipx`, then a private virtual environment under `~/.nano-agent`. Setup starts after installation. To install without opening setup, pass `--no-setup`; to preview only, use `--dry-run`. `--from SPEC` selects a source such as a local checkout or wheel.

## Setup and first run

Choose a provider and model in the wizard. Enter API keys through its hidden prompt or a supported input method; never put keys in shell history. The local data home defaults to `~/.nano-agent`. Setup writes configuration and secrets there with restrictive permissions where the OS supports them.

```bash
nano-agent doctor --offline
nano-agent start
nano-agent status
```

Open the private console URL printed during setup. Run `nano-agent token` to print a login URL again; treat that URL as a password. Keep it private.

## Update and remove

Use `nano-agent update` to update the installed package. To remove it, run `nano-agent uninstall` and review the prompt: deleting the data directory removes local memory, skills, logs and settings. Back up data before removal if you may need it later.

## From source

```bash
python -m pip install -e ".[dev]"
python -m nanoagent --help
```

See [CONFIG.md](CONFIG.md), [PROVIDERS.md](PROVIDERS.md), and [LINE_SETUP.md](LINE_SETUP.md) for optional integrations.
