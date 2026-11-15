# Install nano Agent

nano Agent supports native Windows, Linux, macOS and WSL with Python 3.11 or newer. The installers do not request administrator rights or edit shell startup files. They display the source and installation plan before changing anything.

## Installer

On Linux, macOS or WSL, download and inspect the script, then run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/julachok20/nano-agent/main/install.sh # scan:allow
less install.sh
bash install.sh
```

On native Windows, use PowerShell:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/julachok20/nano-agent/main/install.ps1 -OutFile install.ps1 # scan:allow
Get-Content .\install.ps1
.\install.ps1
```

The short form is `irm https://raw.githubusercontent.com/julachok20/nano-agent/main/install.ps1 | iex`, but reading the downloaded script first is recommended. The Windows installer can offer to install Python 3.12 with `winget --scope user` if Python is missing; it asks first. <!-- scan:allow -->

Both scripts prefer `uv`, then `pipx`, then a private virtual environment under `~/.nano-agent` (Windows: `%USERPROFILE%\.nano-agent`). Setup starts after installation. On Linux and macOS use `--no-setup`, `--dry-run`, `--from SPEC`; on Windows use `-NoSetup`, `-DryRun`, `-From SPEC`. For example, `bash install.sh --dry-run --from .` or `.\install.ps1 -DryRun -From .`. A local checkout, wheel, or pip URL can be used as `SPEC`.

If the fallback venv is used, the executable lives in `~/.local/bin/nano-agent` on Unix. On Windows it lives in `%USERPROFILE%\.nano-agent\venv\Scripts\nano-agent.exe`; a `nano-agent.cmd` launcher is also placed in `%USERPROFILE%\.local\bin`. Add that bin folder to your PATH if you want to use the short command in every new shell.

## Setup and first run

Choose **Quick setup** for language, model and key with local dashboard defaults. Use **Custom setup** for network access and optional integrations. Enter API keys through the hidden prompt or a supported input method; never put keys in shell history. The local data home defaults to `~/.nano-agent`. Setup writes configuration and secrets there with restrictive permissions where the OS supports them.

```bash
nano-agent doctor --offline
nano-agent start
nano-agent status
```

Interactive setup starts the local service, opens the private dashboard, and enters terminal chat. Run `nano-agent launch` to do that again; `nano-agent launch --no-browser` or `--no-chat` skips either part. Type `/dashboard` inside terminal chat to reopen the browser and `/quit` to leave chat. The service continues until `nano-agent stop`. Run `nano-agent token` to print a login URL if automatic browser opening is unavailable; treat that URL as a password. Keep it private. On Windows, if the short command is not yet on PATH, use the full executable path above.

## Update and remove

Use `nano-agent update` to update the installed package. To remove it, run `nano-agent uninstall` and review the prompt: deleting the data directory removes local memory, skills, logs and settings. Back up data before removal if you may need it later.

## From source

```bash
python -m pip install -e ".[dev]"
python -m nanoagent --help
```

See [CONFIG.md](CONFIG.md), [PROVIDERS.md](PROVIDERS.md), and [LINE_SETUP.md](LINE_SETUP.md) for optional integrations.
