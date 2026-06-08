"""SGR (Select Graphic Rendition) state tracking and sanitization."""

import copy
import re
from dataclasses import dataclass, field

# Matches a complete SGR escape sequence: ESC [ <params> m
SGR_RE = re.compile(r"\033\[([0-9;]*)m")


@dataclass
class SgrState:
    """Active SGR (Select Graphic Rendition) terminal attribute state.

    Tracks which visual attributes are currently "on" so that a slice of
    lines can be prefixed with the correct escape sequence to reproduce the
    screen appearance, and so the last line can be closed with a reset.

    fg/bg are:
      None                 – default terminal colour
      int                  – named colour code (30-37, 39, 40-47, 49, 90-97, 100-107)
      tuple[int, ...]      – extended colour, e.g. (38, 5, 200) or (38, 2, r, g, b)
    """

    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    blink: bool = False
    reverse: bool = False
    conceal: bool = False
    strikethrough: bool = False
    fg: int | tuple[int, ...] | None = field(default=None)
    bg: int | tuple[int, ...] | None = field(default=None)

    def is_default(self) -> bool:
        return (
            not any(
                [
                    self.bold,
                    self.dim,
                    self.italic,
                    self.underline,
                    self.blink,
                    self.reverse,
                    self.conceal,
                    self.strikethrough,
                ]
            )
            and self.fg is None
            and self.bg is None
        )

    def as_escape(self) -> str:
        """Return an SGR sequence that reproduces this state from any prior state.

        Always begins with a reset (code 0) so the sequence is unconditionally
        correct regardless of the terminal's current state.
        """
        if self.is_default():
            return "\033[0m"
        codes: list[str] = ["0"]
        if self.bold:
            codes.append("1")
        if self.dim:
            codes.append("2")
        if self.italic:
            codes.append("3")
        if self.underline:
            codes.append("4")
        if self.blink:
            codes.append("5")
        if self.reverse:
            codes.append("7")
        if self.conceal:
            codes.append("8")
        if self.strikethrough:
            codes.append("9")
        if self.fg is not None:
            if isinstance(self.fg, tuple):
                codes.extend(str(x) for x in self.fg)
            else:
                codes.append(str(self.fg))
        if self.bg is not None:
            if isinstance(self.bg, tuple):
                codes.extend(str(x) for x in self.bg)
            else:
                codes.append(str(self.bg))
        return f"\033[{';'.join(codes)}m"

    def apply(self, line: str) -> None:
        """Update state by consuming every SGR sequence in line."""
        for m in SGR_RE.finditer(line):
            apply_sgr(self, m.group(1))


def apply_sgr(state: SgrState, params: str) -> None:
    """Apply a single SGR parameter string (the part between ESC[ and m) to state."""
    # Split on semicolons; an empty string means code 0 (full reset).
    parts = params.split(";") if params else ["0"]
    i = 0
    while i < len(parts):
        try:
            code = int(parts[i])
        except ValueError:
            i += 1
            continue

        if code == 0:
            # Full reset
            state.bold = False
            state.dim = False
            state.italic = False
            state.underline = False
            state.blink = False
            state.reverse = False
            state.conceal = False
            state.strikethrough = False
            state.fg = None
            state.bg = None
        elif code == 1:
            state.bold = True
        elif code == 2:
            state.dim = True
        elif code == 3:
            state.italic = True
        elif code == 4:
            state.underline = True
        elif code == 5:
            state.blink = True
        elif code == 7:
            state.reverse = True
        elif code == 8:
            state.conceal = True
        elif code == 9:
            state.strikethrough = True
        elif code == 22:
            state.bold = False
            state.dim = False
        elif code == 23:
            state.italic = False
        elif code == 24:
            state.underline = False
        elif code == 25:
            state.blink = False
        elif code == 27:
            state.reverse = False
        elif code == 28:
            state.conceal = False
        elif code == 29:
            state.strikethrough = False
        elif 30 <= code <= 37:
            state.fg = code
        elif code == 38:
            # Extended fg colour: 38;5;n  or  38;2;r;g;b
            if i + 1 < len(parts):
                kind = int(parts[i + 1])
                if kind == 5 and i + 2 < len(parts):
                    state.fg = (38, 5, int(parts[i + 2]))
                    i += 2
                elif kind == 2 and i + 4 < len(parts):
                    state.fg = (38, 2, int(parts[i + 2]), int(parts[i + 3]), int(parts[i + 4]))
                    i += 4
        elif code == 39:
            state.fg = None
        elif 40 <= code <= 47:
            state.bg = code
        elif code == 48:
            # Extended bg colour: 48;5;n  or  48;2;r;g;b
            if i + 1 < len(parts):
                kind = int(parts[i + 1])
                if kind == 5 and i + 2 < len(parts):
                    state.bg = (48, 5, int(parts[i + 2]))
                    i += 2
                elif kind == 2 and i + 4 < len(parts):
                    state.bg = (48, 2, int(parts[i + 2]), int(parts[i + 3]), int(parts[i + 4]))
                    i += 4
        elif code == 49:
            state.bg = None
        elif 90 <= code <= 97:
            state.fg = code
        elif 100 <= code <= 107:
            state.bg = code

        i += 1


def strip_sgr(line: str) -> str:
    """Remove all SGR escape sequences from a line, leaving only visible text."""
    return SGR_RE.sub("", line)


def sanitize_sgr_slice(all_lines: list[str], selected: list[int]) -> list[str]:
    """Return selected lines with correct SGR prefix/suffix for terminal-safe output.

    When escape_codes=True and only a subset of lines is emitted (head, tail,
    grep), SGR state established before the slice is invisible to the terminal.
    This function:
      - Computes the SGR state at the start of every line by simulating the
        full sequence from line 0.
      - Prefixes each selected line with an SGR sequence that brings the
        terminal to the correct state (only when it differs from what was last
        emitted).
      - Appends \\033[0m after the final line if any attributes are still active.
    """
    if not selected:
        return []

    # Build the SGR state at the *start* of each line (before that line's own codes).
    states: list[SgrState] = []
    state = SgrState()
    for line in all_lines:
        states.append(copy.copy(state))
        state.apply(line)

    result: list[str] = []
    current = SgrState()  # what the terminal is assumed to know so far

    for idx in selected:
        required = states[idx]
        if required != current:
            result.append(required.as_escape() + all_lines[idx])
            current = copy.copy(required)
        else:
            result.append(all_lines[idx])
        current.apply(all_lines[idx])

    # Close any attributes left open by the last output line.
    if not current.is_default():
        result[-1] += "\033[0m"

    return result
