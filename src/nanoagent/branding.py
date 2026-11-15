"""Shared, dependency-free terminal wordmark."""
from __future__ import annotations

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
    if width < 58:
        return ["NANO AGENT"]
    white = "\x1b[1;38;2;245;242;238m" if color else ""
    orange = "\x1b[1;38;2;255;112;32m" if color else ""
    reset = "\x1b[0m" if color else ""
    return [f"{white}{left}{reset}    {orange}{right}{reset}" for left, right in zip(NANO, AGENT, strict=True)]
