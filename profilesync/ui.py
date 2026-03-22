# Copyright 2026 Duke
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""UI utilities for profilesync - colors, prompts, and display functions."""

from __future__ import annotations

import os
import platform
import sys

# Cross-platform colored terminal output
COLORAMA_AVAILABLE = False
try:
    import colorama
    colorama.init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    # colorama not installed - colors will be disabled
    pass


class Colors:
    """ANSI color codes for terminal output"""
    # Basic colors
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[34m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'

    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def color(text: str, color_code: str, bold: bool = False) -> str:
    """Wrap text in ANSI color codes (cross-platform with colorama)"""
    # Disable colors if not in a TTY or colorama not available
    if not sys.stdout.isatty() or not COLORAMA_AVAILABLE:
        return text

    prefix = f"{Colors.BOLD}{color_code}" if bold else color_code
    return f"{prefix}{text}{Colors.RESET}"


def success(text: str) -> str:
    """Green text for success messages"""
    return color(text, Colors.GREEN)


def warning(text: str) -> str:
    """Yellow text for warnings"""
    return color(text, Colors.YELLOW)


def error(text: str) -> str:
    """Red text for errors"""
    return color(text, Colors.RED)


def info(text: str) -> str:
    """Magenta text for informational messages (counts, etc.)"""
    return color(text, Colors.MAGENTA)


def highlight(text: str) -> str:
    """Bold white text for emphasis"""
    return color(text, Colors.WHITE, bold=True)


def dim(text: str) -> str:
    """Dimmed text for less important info - using blue for better readability"""
    return color(text, Colors.BLUE)


def get_check_symbol() -> str:
    """Get appropriate check/success symbol for the platform"""
    # Use ASCII-compatible symbols for Windows compatibility
    # Unicode checkmarks don't display properly in Windows terminal
    system = platform.system()
    if system == "Windows":
        return "[OK]"  # ASCII-safe for Windows
    else:
        return "✓"  # Unicode checkmark for Unix/macOS


def confirm(prompt: str, default: bool = False) -> bool:
    """Ask user for yes/no confirmation"""
    suffix = " [Y/n] " if default else " [y/N] "
    ans = input(prompt + suffix).strip().lower()
    if ans == "":
        return default
    return ans in ("y", "yes")


# ---- Interactive arrow-key pickers (rich-based) --------------------------------

def _is_interactive() -> bool:
    """Check if terminal supports interactive pickers."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import msvcrt  # noqa: F401
            return True
        except ImportError:
            return False
    else:
        try:
            import tty, termios  # noqa: F401
            return True
        except ImportError:
            return False


def _read_key() -> str | None:
    """Read a single keypress, returning a normalized string.

    Returns: "up", "down", "space", "enter", "escape", or the character.
    """
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\xe0", "\x00"):
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(ch2)
        if ch == "\r":
            return "enter"
        if ch == " ":
            return "space"
        if ch == "\x1b":
            return "escape"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    return {"A": "up", "B": "down"}.get(ch3)
                return "escape"
            if ch in ("\r", "\n"):
                return "enter"
            if ch == " ":
                return "space"
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _build_picker_renderable(
    items: list[str],
    cursor: int,
    checked: list[bool] | None,
    hint: str,
):
    """Build a rich Text renderable for the picker display."""
    from rich.text import Text

    output = Text()
    for i, label in enumerate(items):
        is_cursor = i == cursor
        arrow = "> " if is_cursor else "  "

        if checked is not None:
            box = "[x] " if checked[i] else "[ ] "
        else:
            box = ""

        line = f"  {arrow}{box}{label}\n"
        style = "bold white" if is_cursor else ""
        output.append(line, style=style)

    output.append(f"  {hint}\n", style="dim blue")
    return output


def pick_many(
    title: str,
    items: list[str],
    checked: list[bool] | None = None,
) -> list[int] | None:
    """Interactive multi-select picker with arrow keys.

    Args:
        title: Header text printed above the picker.
        items: Labels to display.
        checked: Initial checked state per item (default: all unchecked).

    Returns:
        List of selected indices, or None if cancelled.
    """
    if not items:
        return []

    n = len(items)
    if checked is None:
        checked = [False] * n
    else:
        checked = list(checked)
    cursor = 0

    hint = "↑↓ move  SPACE toggle  a all  n none  ENTER confirm  q cancel"

    # ---- Non-TTY fallback ----
    if not _is_interactive():
        print(title)
        for i, label in enumerate(items, 1):
            mark = "x" if checked[i - 1] else " "
            print(f"  {i}) [{mark}] {label}")
        raw = input("Select (comma-separated, ENTER for marked): ").strip()
        if raw.lower() == "q":
            return None
        if not raw:
            return [i for i in range(n) if checked[i]]
        selected = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= n:
                selected.append(int(part) - 1)
        return selected

    # ---- Interactive picker ----
    from rich.console import Console
    from rich.live import Live

    console = Console()
    console.print(title)

    renderable = _build_picker_renderable(items, cursor, checked, hint)
    with Live(
        renderable, console=console, auto_refresh=False, transient=True
    ) as live:
        try:
            while True:
                key = _read_key()
                if key == "up":
                    cursor = (cursor - 1) % n
                elif key == "down":
                    cursor = (cursor + 1) % n
                elif key == "space":
                    checked[cursor] = not checked[cursor]
                elif key == "a":
                    for i in range(n):
                        checked[i] = True
                elif key == "n":
                    for i in range(n):
                        checked[i] = False
                elif key == "enter":
                    return [i for i in range(n) if checked[i]]
                elif key in ("q", "escape"):
                    return None
                else:
                    continue
                live.update(
                    _build_picker_renderable(items, cursor, checked, hint),
                    refresh=True,
                )
        except KeyboardInterrupt:
            return None


def pick_one(
    title: str,
    items: list[str],
    default: int = 0,
) -> int | None:
    """Interactive single-select picker with arrow keys.

    Args:
        title: Header text printed above the picker.
        items: Labels to display.
        default: Initially highlighted index.

    Returns:
        Selected index, or None if cancelled.
    """
    if not items:
        return None

    n = len(items)
    cursor = default
    hint = "↑↓ move  ENTER select  q cancel"

    # ---- Non-TTY fallback ----
    if not _is_interactive():
        print(title)
        for i, label in enumerate(items, 1):
            print(f"  {i}) {label}")
        raw = input(f"Select [default {default + 1}]: ").strip()
        if raw.lower() == "q":
            return None
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw) - 1
        return default

    # ---- Interactive picker ----
    from rich.console import Console
    from rich.live import Live

    console = Console()
    console.print(title)

    renderable = _build_picker_renderable(items, cursor, None, hint)
    with Live(
        renderable, console=console, auto_refresh=False, transient=True
    ) as live:
        try:
            while True:
                key = _read_key()
                if key == "up":
                    cursor = (cursor - 1) % n
                elif key == "down":
                    cursor = (cursor + 1) % n
                elif key == "enter":
                    return cursor
                elif key in ("q", "escape"):
                    return None
                else:
                    continue
                live.update(
                    _build_picker_renderable(items, cursor, None, hint),
                    refresh=True,
                )
        except KeyboardInterrupt:
            return None
