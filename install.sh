#!/usr/bin/env bash
# nano Agent installer for Linux, macOS and WSL. No sudo, no system changes: it installs into your home folder only.
#
#   curl -fsSL https://raw.githubusercontent.com/julachok20/nano-agent/main/install.sh | bash
#   (safer: download it, read it, then run it:  curl -fsSLO <same url> && less install.sh && bash install.sh)
#
# What it does, in order (it prints the plan before it starts):
#   1. checks the OS (Linux, macOS, WSL) and finds Python 3.11 or newer
#   2. installs the `nanoagent` package into an isolated environment, using the first of:
#        uv tool install  |  pipx install  |  a private venv in ~/.nano-agent/venv (+ a link in ~/.local/bin)
#   3. runs `nano-agent setup` (interactive wizard) unless you pass --no-setup
# It never edits your shell profile, never uses sudo and never sends anything anywhere except to download the package.
#
# Options:  --no-setup   --yes   --dry-run   --method auto|uv|pipx|venv   --from SPEC (pip spec: folder, wheel, package or URL)   --ref GIT_REF   --help
# Environment: NANO_AGENT_REPO (default julachok20/nano-agent)  NANO_AGENT_REF  NANO_AGENT_SPEC  NANO_AGENT_FROM_PYPI=1  NANO_AGENT_HOME
set -euo pipefail

REPO="${NANO_AGENT_REPO:-julachok20/nano-agent}"
REF="${NANO_AGENT_REF:-main}"
SPEC="${NANO_AGENT_SPEC:-}"
NO_SETUP=0
YES=0
DRY=0
INSTALL_METHOD="auto"

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

frame() {
  [ -t 1 ] || return 0
  local step="$1" title="$2"
  shift 2
  printf '\033[2J\033[H'
  printf '  \033[1;38;2;255;112;32m◆\033[0m  \033[1;38;2;248;248;246mNANO AGENT\033[0m  \033[38;2;125;137;149m/  INSTALLER\033[0m\n'
  printf '  \033[38;2;70;78;88m────────────────────────────────────────────────────────────\033[0m\n'
  local cols
  cols=$(tput cols 2>/dev/null || echo 80)
  if [ "$cols" -ge 60 ]; then
    printf '  \033[1;38;2;248;248;246m╭╮ ╭╮ ╭──╮ ╭╮ ╭╮ ╭──╮\033[0m    \033[1;38;2;255;112;32m╭──╮ ╭──╮ ╭─── ╭╮ ╭╮ ┳━━┳\033[0m\n'
    printf '  \033[1;38;2;248;248;246m│╰╮│ ├──┤ │╰╮│ │  │\033[0m    \033[1;38;2;255;112;32m├──┤ │ ╭╮ ├──  │╰╮│   ┃\033[0m\n'
    printf '  \033[1;38;2;248;248;246m╵ ╰╯ ╵  ╵ ╵ ╰╯ ╰──╯\033[0m    \033[1;38;2;255;112;32m╵  ╵ ╰──╯ ╰─── ╵ ╰╯   ╵\033[0m\n'
  else
    printf '  \033[1;38;2;248;248;246mNANO \033[1;38;2;255;112;32mAGENT\033[0m\n'
  fi
  printf '\n  \033[38;2;125;137;149mPERSONAL AI  /  LOCAL FIRST\033[0m\n\n'
  printf '  '
  local i label
  for i in 1 2 3 4; do
    case "$i" in 1) label='CHECK' ;; 2) label='INSTALL' ;; 3) label='SET UP' ;; 4) label='LAUNCH' ;; esac
    if [ "$i" -eq "$step" ]; then
      printf '\033[1;38;2;255;112;32m%02d %s\033[0m' "$i" "$label"
    elif [ "$i" -lt "$step" ]; then
      printf '\033[38;2;125;185;150m✓ %s\033[0m' "$label"
    else
      printf '\033[38;2;115;128;142m%02d %s\033[0m' "$i" "$label"
    fi
    [ "$i" -eq 4 ] || printf '  \033[38;2;70;78;88m/\033[0m  '
  done
  printf '\n\n  \033[38;2;70;78;88m────────────────────────────────────────────────────────────\033[0m\n'
  printf '  \033[1;38;2;248;248;246m%s\033[0m\n' "$title"
  printf '  \033[38;2;70;78;88m────────────────────────────────────────────────────────────\033[0m\n'
  while [ $# -gt 0 ]; do
    printf '  \033[38;2;190;202;214m%s\033[0m\n' "$1"
    shift
  done
  printf '\n'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-setup) NO_SETUP=1 ;;
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    --method) shift; [ $# -gt 0 ] || die "--method needs a value"; INSTALL_METHOD="$1" ;;
    --from) shift; [ $# -gt 0 ] || die "--from needs a value"; SPEC="$1" ;;
    --ref) shift; [ $# -gt 0 ] || die "--ref needs a value"; REF="$1" ;;
    -h|--help) sed -n '2,19p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done

# The installer itself owns the first screen, before checking or changing anything.
frame 1 "Checking this computer…"

# ---- 1. OS and Python ------------------------------------------------------
OS="$(uname -s 2>/dev/null || echo unknown)"
case "$OS" in
  Linux|Darwin) ;;
  MINGW*|MSYS*|CYGWIN*) die "native Windows is not supported in v0.1. Install WSL (wsl --install) and run this inside Ubuntu. See docs/INSTALL.md." ;;
  *) die "unsupported OS: $OS (Linux, macOS and WSL are supported)" ;;
esac

PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"
    break
  fi
done
[ -n "$PY" ] || die "Python 3.11 or newer was not found. Install it (for example: sudo apt install python3 python3-venv, or brew install python) and run this again."
PYV="$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"

if [ -z "$SPEC" ]; then
  if [ "${NANO_AGENT_FROM_PYPI:-0}" = "1" ]; then
    SPEC="nanoagent"
  else
    SPEC="https://codeload.github.com/${REPO}/tar.gz/${REF}"
  fi
fi

# ---- 2. choose how to install ---------------------------------------------
HOME_DIR="${NANO_AGENT_HOME:-$HOME/.nano-agent}"
BIN_DIR="${NANO_AGENT_BIN_DIR:-$HOME/.local/bin}"
case "$INSTALL_METHOD" in
  auto)
    if command -v uv >/dev/null 2>&1; then METHOD="uv"
    elif command -v pipx >/dev/null 2>&1; then METHOD="pipx"
    else METHOD="venv"; fi ;;
  uv|pipx) command -v "$INSTALL_METHOD" >/dev/null 2>&1 || die "$INSTALL_METHOD was selected but is not installed"; METHOD="$INSTALL_METHOD" ;;
  venv) METHOD="venv" ;;
  *) die "unknown method: $INSTALL_METHOD (choose auto, uv, pipx or venv)" ;;
esac
case "$METHOD" in
  uv) PLAN="uv tool install --python $PY --force \"$SPEC\"   (isolated tool environment managed by uv)" ;;
  pipx) PLAN="pipx install --python $PY --force \"$SPEC\"   (isolated environment managed by pipx)" ;;
  venv) PLAN="$PY -m venv \"$HOME_DIR/venv\" && \"$HOME_DIR/venv/bin/pip\" install \"$SPEC\"; link $BIN_DIR/nano-agent -> the venv" ;;
esac

if [ -t 1 ]; then
  frame 2 "Ready to install" "OS: $OS · Python: $PYV" "Source: $SPEC" \
    "Method: $METHOD · Data: $HOME_DIR" "Next: install package → configure assistant → open console"
else
  say "nano Agent installer"
  say "  OS:        $OS"
  say "  Python:    $PYV ($PY)"
  say "  Source:    $SPEC"
  say "  Method:    $METHOD"
  say "  Will run:  $PLAN"
  say "  Data dir:  $HOME_DIR (created later by 'nano-agent setup')"
  say "  No sudo, no shell-profile edits."
fi
if [ "$DRY" = "1" ]; then say "dry run: nothing was changed."; exit 0; fi

if [ "$YES" = "0" ] && [ -r /dev/tty ] && [ -t 1 ]; then
  printf '  \033[1;38;2;255;112;32m›\033[0m  Press Enter to install  \033[38;2;115;128;142m(n to cancel)\033[0m '
  read -r ans </dev/tty || ans=""
  case "${ans:-y}" in n|N|no|NO) say "aborted."; exit 1 ;; esac
fi

# ---- install ---------------------------------------------------------------
BIN=""
case "$METHOD" in
  uv)
    frame 2 "Installing nano Agent with uv…"
    uv tool install --python "$PY" --force "$SPEC"
    BIN="$(command -v nano-agent 2>/dev/null || true)"
    [ -n "$BIN" ] || BIN="$(uv tool dir --bin 2>/dev/null || echo "$BIN_DIR")/nano-agent"
    ;;
  pipx)
    frame 2 "Installing nano Agent with pipx…"
    pipx install --python "$PY" --force "$SPEC"
    BIN="$(command -v nano-agent 2>/dev/null || echo "$BIN_DIR/nano-agent")"
    ;;
  venv)
    frame 2 "Preparing your private environment…"
    mkdir -p "$HOME_DIR"
    "$PY" -m venv "$HOME_DIR/venv" || die "could not create a venv. On Debian/Ubuntu run: sudo apt install python3-venv"
    frame 2 "Installing nano Agent into its private environment…"
    "$HOME_DIR/venv/bin/python" -m pip install --quiet --disable-pip-version-check "$SPEC"
    mkdir -p "$BIN_DIR"
    ln -sf "$HOME_DIR/venv/bin/nano-agent" "$BIN_DIR/nano-agent"
    BIN="$BIN_DIR/nano-agent"
    ;;
esac

[ -x "$BIN" ] || die "installation finished but $BIN was not found. Check the output above."
"$BIN" --version || die "the installed command does not run"
case ":$PATH:" in
  *":$(dirname "$BIN"):"*) ;;
  *) say ""; say "Note: $(dirname "$BIN") is not on your PATH. Add this line to your shell profile:"; say "  export PATH=\"$(dirname "$BIN"):\$PATH\"" ;;
esac

# ---- 3. setup ---------------------------------------------------------------
if [ "$NO_SETUP" = "1" ]; then
  say ""; say "Installed. Next: nano-agent setup"
  exit 0
fi
say ""
if [ -r /dev/tty ] && [ -t 1 ]; then
  frame 3 "Installation complete · opening setup…"
  exec "$BIN" setup </dev/tty
fi
say "Installed. No terminal for the wizard here, so run it yourself: nano-agent setup"
