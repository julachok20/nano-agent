"""Shared, dependency-free terminal wordmark and panels."""
from __future__ import annotations

import re
import textwrap

ORANGE = "\x1b[1;38;2;255;112;32m"
WHITE = "\x1b[1;38;2;248;248;246m"
MUTED = "\x1b[38;2;125;137;149m"
RULE = "\x1b[38;2;70;78;88m"
RESET = "\x1b[0m"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

NANO = (
    "█   █  ███  █   █  ███ ",
    "██  █ █   █ ██  █ █   █",
    "█ █ █ █████ █ █ █ █   █",
    "█  ██ █   █ █  ██ █   █",
    "█   █ █   █ █   █  ███ ",
)
AGENT = (
    " ███   ████ █████ █   █ █████",
    "█   █ █     █     ██  █   █  ",
    "█████ █  ██ ████  █ █ █   █  ",
    "█   █ █   █ █     █  ██   █  ",
    "█   █  ███  █████ █   █   █  ",
)


def wordmark(*, color: bool = True, width: int = 80) -> list[str]:
    """Return a large wordmark where it fits, or a compact one on narrow TTYs."""
    if width < 62:
        return ["NANO AGENT"]
    shades = ("255;140;59", "255;126;42", "255;112;32", "239;95;28", "222;82;24")
    agent_colors = [f"\x1b[1;38;2;{shade}m" for shade in shades]
    return [
        f"{WHITE if color else ''}{left}{RESET if color else ''}    "
        f"{agent_colors[i] if color else ''}{right}{RESET if color else ''}"
        for i, (left, right) in enumerate(zip(NANO, AGENT, strict=True))
    ]


def banner(section: str, *, version: str = "", width: int = 80, compact: bool = False) -> list[str]:
    """Shared terminal masthead for setup, chat, and the command line."""
    rule = "─" * min(70, max(20, width - 4))
    heading = f"  {ORANGE}◆{RESET}  {WHITE}NANO AGENT{RESET}  {MUTED}/ {section.upper()}"
    if version and width >= 50:
        heading += f"  ·  {version}"
    lines = [heading + RESET, f"  {RULE}{rule}{RESET}", ""]
    if compact:
        lines.extend((f"  {ORANGE}▌{RESET}  {WHITE}NANO {ORANGE}AGENT{RESET}",
                      f"  {ORANGE}▔▔{RESET}  {MUTED}LOCAL FIRST{RESET}"))
    elif width >= 62:
        lines.extend(f"  {ORANGE}▌{RESET}  {row}" for row in wordmark(width=width))
        lines.append(f"  {ORANGE}▔▔{RESET}  {MUTED}PERSONAL AI  ·  LOCAL FIRST  ·  PRIVATE BY DEFAULT{RESET}")
    else:
        lines.extend((f"  {ORANGE}▌{RESET}  {WHITE}NANO {ORANGE}AGENT{RESET}",
                      f"  {ORANGE}▔▔{RESET}  {MUTED}LOCAL FIRST{RESET}"))
    return lines


def card(title: str, body: list[str], *, width: int = 80) -> list[str]:
    """Wrap a terminal panel without breaking its border at common widths."""
    inner = min(68, max(20, width - 6))
    border = "─" * (inner + 2)
    lines = [f"  {RULE}╭{border}╮{RESET}"]
    items = [f"{ORANGE}◆{RESET} {WHITE}{title}{RESET}", *body]
    for item in items:
        plain = _ANSI.sub("", item)
        chunks = [item] if len(plain) <= inner else textwrap.wrap(plain, width=inner,
                                                                 replace_whitespace=False, drop_whitespace=False)
        for chunk in chunks:
            visible = len(_ANSI.sub("", chunk))
            lines.append(f"  {RULE}│{RESET} {chunk}{' ' * max(0, inner - visible)} {RULE}│{RESET}")
    lines.append(f"  {RULE}╰{border}╯{RESET}")
    return lines
