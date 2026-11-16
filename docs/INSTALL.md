# Install nano Agent

nano Agent supports native Windows, Linux, macOS and WSL with Python 3.11 or newer. The installers do not request administrator rights or edit shell startup files. They display the source and installation plan before changing anything.

## Installer

From a local checkout on Linux, macOS or WSL:

```bash
bash install.sh
```

From a local checkout on native Windows, use PowerShell:

```powershell
.\install.ps1
```

The local installer automatically uses the checkout containing the script. One command installs the package, opens the setup wizard, then starts the assistant, dashboard, and terminal chat. Once the repository is public, Linux, macOS, and WSL can use the short hosted command:

```bash
curl -fsSL https://raw.githubusercontent.com/julachok20/nano-agent/main/install.sh | bash
```

On native Windows, the equivalent PowerShell command is `irm https://raw.githubusercontent.com/julachok20/nano-agent/main/install.ps1 | iex`. A private repository gives HTTP 404 to unauthenticated users. If you want the shell to stop on a download failure, use `curl -fsSLo nano-agent-install.sh https://raw.githubusercontent.com/julachok20/nano-agent/main/install.sh && bash nano-agent-install.sh`; the `&&` prevents an old local script from running after a failed download. The Windows installer can offer to install Python 3.12 with `winget --scope user` if Python is missing; it asks first.

Both scripts prefer `uv`, then `pipx`, then a private virtual environment under `~/.nano-agent` (Windows: `%USERPROFILE%\.nano-agent`). Setup starts after installation. On Linux and macOS use `--no-setup`, `--dry-run`, `--from SPEC`; on Windows use `-NoSetup`, `-DryRun`, `-From SPEC`. For example, `bash install.sh --dry-run` or `.\install.ps1 -DryRun`. On Linux, macOS, or WSL, `--method venv` explicitly selects the private virtual environment, even when `uv` or `pipx` is installed. A local checkout, wheel, or pip URL can be used as `SPEC`.

If the fallback venv is used, the executable lives in `~/.local/bin/nano-agent` on Unix. On Windows it lives in `%USERPROFILE%\.nano-agent\venv\Scripts\nano-agent.exe`; a `nano-agent.cmd` launcher is also placed in `%USERPROFILE%\.local\bin`. Add that bin folder to your PATH if you want to use the short command in every new shell.

## Setup and first run

Choose **Quick setup** for language, model, key, and connector choices with local dashboard defaults. Both modes ask whether to connect LINE now, later, or use only the dashboard and terminal chat, and whether to prepare Google for later. Use **Custom setup** for network access, storage, voice, and sandbox options. LINE can save its secret and token during Quick setup, but receiving messages requires a public HTTPS webhook configured afterward. Enter API keys through the hidden prompt or a supported input method; never put keys in shell history. The local data home defaults to `~/.nano-agent`. Setup writes configuration and secrets there with restrictive permissions where the OS supports them. On a compatible interactive terminal, the installer and wizard use alternate screens that disappear from scrollback when setup ends. If installation fails, the installer restores the normal screen and prints an error; rerun with `NO_COLOR=1 bash install.sh` for full command output.

```bash
nano-agent doctor --offline
nano-agent start
nano-agent status
```

Interactive setup starts the local service, opens the private dashboard, and enters terminal chat. Run `nano-agent launch` to do that again; `nano-agent launch --no-browser` or `--no-chat` skips either part. Type `/dashboard` inside terminal chat to reopen the browser and `/quit` to leave chat. The service continues until `nano-agent stop`. Run `nano-agent token` to print a login URL if automatic browser opening is unavailable; treat that URL as a password. Keep it private. On Windows, if the short command is not yet on PATH, use the full executable path above.

## Update and remove

Use `nano-agent update` to update the installed package. `nano-agent uninstall` stops the service and keeps local data. `nano-agent uninstall --purge` also deletes memory, skills, logs, and settings after confirmation. Back up data before purging if you may need it later.

## Expected result and troubleshooting

Installation prints the detected OS, Python interpreter, source, method, and data location before asking to continue. Interactive setup then offers Quick or Custom setup, starts the local service, opens the console, and starts terminal chat. Check with `nano-agent status` and `nano-agent doctor --offline`; a healthy local service reports a console URL on `127.0.0.1` and no failed mandatory checks.

If the download URL returns 404, run `bash install.sh` (or `.\install.ps1` on Windows) from the local checkout until the repository is public. If `nano-agent` is not found after a fallback venv install, use the full executable path above or add its bin directory to PATH. If startup fails, run `nano-agent logs --follow` and `nano-agent doctor --offline` before changing configuration.

## From source

```bash
python -m pip install -e ".[dev]"
python -m nanoagent --help
```

See [CONFIG.md](CONFIG.md), [PROVIDERS.md](PROVIDERS.md), and [LINE_SETUP.md](LINE_SETUP.md) for optional integrations.
