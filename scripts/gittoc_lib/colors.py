"""ANSI terminal color helpers for gittoc output.

Colors are applied only when sys.stdout is a TTY. All public functions
return plain strings when colors are disabled, so callers need no
conditional logic.
"""

from __future__ import annotations

import sys

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_DIM_INVERSE = "\033[30;100m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_BRIGHT_BLUE = "\033[94m"


def _c(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes if stdout is a TTY."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + _RESET


def issue_id(text: str) -> str:
    return _c(text, _BOLD, _CYAN)


def priority(n: int) -> str:
    label = f"p{n}"
    if n == 1:
        return _c(label, _RED)
    if n == 2:
        return _c(label, _YELLOW)
    if n == 5:
        return _c(label, _DIM)
    return label


def state_marker(m: str) -> str:
    code = {">": _GREEN, "!": _YELLOW, "~": _RED, "x": _DIM}.get(m)
    return _c(m, code) if code else m


def state(s: str) -> str:
    label = f"[{s}]"
    code = {
        "claimed": _YELLOW,
        "blocked": _RED,
        "closed": _DIM,
        "rejected": _DIM_INVERSE,
    }.get(s)
    return _c(label, code) if code else label


def title(text: str) -> str:
    return _c(text, _BOLD)


def label(text: str) -> str:
    return _c(text, _CYAN)


def count(n: int) -> str:
    return _c(str(n), _YELLOW)


def timestamp(text: str) -> str:
    return _c(text, _DIM)


def event_label(text: str) -> str:
    """Color an event label: green for notes, magenta for other event kinds."""
    if text.startswith("note"):
        return _c(text, _GREEN)
    return _c(text, _MAGENTA)


def actor(text: str) -> str:
    return _c(text, _CYAN)


def deps(text: str) -> str:
    return _c(text, _RED)


def owner(text: str) -> str:
    return _c(text, _BRIGHT_BLUE)


def field_name(text: str) -> str:
    return _c(text, _DIM)
