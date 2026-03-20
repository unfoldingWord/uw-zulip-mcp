"""uW branded ASCII art progress indicator.

Renders the unfoldingWord logo in block characters with a white-to-cerulean
color transition. Used for long-running operations like wait_for_response.

Only renders when stderr is a TTY. Falls back silently in non-TTY environments.
Output goes to stderr exclusively — stdout is reserved for MCP stdio transport.
"""

from __future__ import annotations

import sys
import threading
import time

# uW logo — lowercase u + uppercase W in block characters
UW_LOGO = [
    "            ██          ██",
    "            ██          ██",
    "██    ██    ██    ██    ██",
    "██    ██    ██    ██    ██",
    "██    ██    ██   ████   ██",
    "██    ██     ██ ██  ██ ██ ",
    " ██████       ████  ████  ",
    "  ████         ██    ██   ",
]

# Truecolor ANSI gradient: white -> cerulean
_GRADIENT = [
    (255, 255, 255),  # white
    (220, 230, 235),  # soft white
    (195, 220, 235),  # pale ice
    (180, 215, 235),  # ice
    (150, 205, 230),  # light ice
    (120, 195, 235),  # light blue
    (80, 175, 225),   # medium blue
    (40, 165, 218),   # approaching cerulean
    (0, 155, 210),    # cerulean
    (0, 135, 190),    # deep cerulean
    (0, 155, 210),    # cerulean (settle)
]

# Breathing pulse colors (indices into a small palette)
_PULSE = [
    (0, 155, 210),    # cerulean
    (0, 135, 190),    # deep
    (0, 155, 210),    # cerulean
    (120, 195, 235),  # light blue
    (0, 155, 210),    # cerulean
]

_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"
_CLEAR_LINE = "\033[2K"


def _rgb(r: int, g: int, b: int) -> str:
    """Generate truecolor ANSI foreground escape."""
    return f"\033[1;38;2;{r};{g};{b}m"


def _reset() -> str:
    return "\033[0m"


def _is_tty() -> bool:
    """Check if stderr is a TTY (safe for animation)."""
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False


def _draw_logo(color_rgb: tuple[int, int, int], status_line: str = "") -> None:
    """Draw the uW logo in a single color with optional status line below."""
    out = sys.stderr
    color = _rgb(*color_rgb)
    rst = _reset()

    # Move cursor to top-left area for logo (use relative positioning)
    # We'll draw from current position downward
    lines = []
    for row in UW_LOGO:
        lines.append(f"  {color}{row}{rst}")
    if status_line:
        lines.append(f"  {color}{status_line}{rst}")
    else:
        lines.append("")

    # Move up to overwrite previous frame
    total_lines = len(UW_LOGO) + 1
    out.write(f"\033[{total_lines}A")
    for line in lines:
        out.write(f"{_CLEAR_LINE}{line}\n")
    out.flush()


def _draw_initial() -> None:
    """Draw initial blank lines to reserve space for the logo."""
    out = sys.stderr
    total_lines = len(UW_LOGO) + 1  # logo + status line
    out.write("\n" * total_lines)
    out.flush()


class UwProgressIndicator:
    """Animated uW progress indicator for long-running operations.

    Usage:
        indicator = UwProgressIndicator(total_seconds=300)
        indicator.start()
        # ... do work ...
        indicator.update(elapsed=60)
        # ... more work ...
        indicator.stop(success=True)

    Only renders in TTY environments. No-ops silently otherwise.
    """

    def __init__(self, total_seconds: int = 300) -> None:
        self.total_seconds = total_seconds
        self._active = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._elapsed = 0.0
        self._tty = _is_tty()

    def start(self) -> None:
        """Start the progress animation in a background thread."""
        if not self._tty:
            return

        self._active = True
        self._stop_event.clear()
        self._elapsed = 0.0

        sys.stderr.write(_HIDE_CURSOR)
        sys.stderr.flush()
        _draw_initial()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Background animation loop."""
        start_time = time.time()

        # Phase 1: Gradient transition (first ~3 seconds)
        for _i, color in enumerate(_GRADIENT):
            if self._stop_event.is_set():
                return
            self._elapsed = time.time() - start_time
            remaining = max(0, self.total_seconds - int(self._elapsed))
            status = f"  waiting... {int(self._elapsed)}s / {self.total_seconds}s"
            _draw_logo(color, status)
            time.sleep(0.15)

        # Phase 2: Breathing pulse while waiting
        pulse_idx = 0
        while not self._stop_event.is_set():
            self._elapsed = time.time() - start_time
            elapsed_int = int(self._elapsed)
            remaining = max(0, self.total_seconds - elapsed_int)

            color = _PULSE[pulse_idx % len(_PULSE)]

            status = f"  waiting... {elapsed_int}s / {self.total_seconds}s"
            if remaining <= 30:
                status += "  ⚠ timeout soon"

            _draw_logo(color, status)

            pulse_idx += 1
            # Slower pulse — ~2s per cycle
            self._stop_event.wait(0.4)

    def stop(self, success: bool = True) -> None:
        """Stop the animation and show final state."""
        if not self._tty or not self._active:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)

        # Final frame
        if success:
            color = (0, 155, 210)  # cerulean
            status = f"  ✓ response received ({int(self._elapsed)}s)"
        else:
            color = (180, 100, 100)  # muted red
            status = f"  ✗ timeout after {self.total_seconds}s"

        _draw_logo(color, status)

        sys.stderr.write(_SHOW_CURSOR)
        sys.stderr.write("\n")
        sys.stderr.flush()
        self._active = False

    def __del__(self) -> None:
        """Ensure cursor is restored if object is garbage collected."""
        if self._active and self._tty:
            try:
                sys.stderr.write(_SHOW_CURSOR)
                sys.stderr.flush()
            except Exception:
                pass
