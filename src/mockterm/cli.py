"""
mockterm - headless terminal utility for AI agents to test TUI programs.
"""

import re
import sys
import time

import click

from mockterm.ansi import sanitize_sgr_slice, strip_sgr
from mockterm.session import (
    DEFAULT_ID,
    capture_pane,
    kill_session,
    require_tmux_session,
    start_session,
)

DEFAULT_COLS = 120
DEFAULT_ROWS = 40


# ---------------------------------------------------------------------------
# parse helper
# ---------------------------------------------------------------------------


def _parse_size(size: str) -> tuple[int, int]:
    """Parse a COLSxROWS string, e.g. '120x40'."""
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        raise click.BadParameter(f"invalid size '{size}', expected COLSxROWS (e.g. 120x40)")
    return int(match.group(1)), int(match.group(2))


@click.group()
def main() -> None:
    """Headless terminal utility for AI agents to test TUI programs.

    mockterm wraps tmux to give agents a way to start, interact with, and
    inspect interactive terminal programs without a real terminal.  Session
    state is kept in .mockterm (INI format) in the current directory so that
    multiple agents can work side-by-side without colliding.

    \b
    QUICK REFERENCE
    ───────────────
    Start a program:
      mockterm start [-s SESSION] [--size COLSxROWS] COMMAND [ARG]...

    \b
    Read screen contents:
      mockterm cat   [-s SESSION] [-e|-i]         # full screen
      mockterm head  [-s SESSION] [-e|-i] [-n N]  # first N lines (default 10)
      mockterm tail  [-s SESSION] [-e|-i] [-n N]  # last N lines  (default 10)

    \b
    Search screen:
      mockterm grep [-s SESSION] [-e|-i] [--wait] [-t SECS]
                    [-A N] [-B N] [-C N] PATTERN
        --wait  poll once/sec until match found (default timeout: 10 s)
        exits 0 on match, 1 on no-match/timeout

    \b
    Send input:
      mockterm send-keys [-s SESSION] [STRING | KEYNAME]...
        key names follow tmux: Enter Escape Tab Up Down C-c C-d etc.

    \b
    Tear down:
      mockterm kill [-s SESSION]

    \b
    SESSIONS
    ────────
    -s SESSION  logical name (default: "default").  Multiple sessions can
    coexist in the same directory.  The tmux session name includes a random
    tag so two agents can use the same logical name without colliding.

    \b
    FLAGS COMMON TO cat/head/tail/grep
    ───────────────────────────────────
    -e / --escape-codes   output ANSI escape codes (default: stripped).
    -i / --image          render output as a PNG and print the file path.
                          Writes to .mockterm-images/ in the current directory.
                          Requires DejaVu Sans Mono or Liberation Mono.
                          Mutually exclusive with -e.
    """


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


@main.command(context_settings={"allow_interspersed_args": False})
@click.option(
    "-s",
    "--session",
    "session_id",
    default=DEFAULT_ID,
    show_default=True,
    help="Session ID (default: 'default').",
)
@click.option(
    "--size",
    "size_str",
    default=f"{DEFAULT_COLS}x{DEFAULT_ROWS}",
    show_default=True,
    metavar="<COLS>x<ROWS>",
    help="Terminal dimensions.",
)
@click.argument("command", nargs=-1, required=True)
def start(session_id: str, size_str: str, command: tuple[str, ...]) -> None:
    """Start a command in a headless terminal session.

    Kills any existing session with the same ID before starting. Session state
    is written to .mockterm in the current directory.

    \b
    Examples:
      mockterm start python -m myapp
      mockterm start -s editor vim myfile.py
      mockterm start --size=80x24 htop
    """
    cols, rows = _parse_size(size_str)
    tmux_session = start_session(session_id, list(command), cols, rows)
    click.echo(f"Started session '{session_id}' (tmux: {tmux_session}, {cols}x{rows})")


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


@main.command()
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
@click.option("--wait", is_flag=True, default=False, help="Poll repeatedly until a match is found.")
@click.option(
    "-t",
    "--timeout",
    "timeout",
    type=float,
    default=10.0,
    show_default=True,
    help="Timeout in seconds when --wait is used.",
)
@click.option("-A", "after", type=int, default=0, metavar="NUM", help="Print NUM lines after each match.")
@click.option("-B", "before", type=int, default=0, metavar="NUM", help="Print NUM lines before each match.")
@click.option(
    "-C",
    "context",
    type=int,
    default=0,
    metavar="NUM",
    help="Print NUM lines before and after each match.",
)
@click.option(
    "-e",
    "--escape-codes",
    is_flag=True,
    default=False,
    help="Preserve ANSI escape codes in output.",
)
@click.option(
    "-i",
    "--image",
    is_flag=True,
    default=False,
    help="Render matched lines as a PNG and print the file path.",
)
@click.argument("pattern")
def grep(
    session_id: str,
    pattern: str,
    wait: bool,
    timeout: float,
    after: int,
    before: int,
    context: int,
    escape_codes: bool,
    image: bool,
) -> None:
    """Search the current screen contents for PATTERN.

    PATTERN is matched against the visible text of each line (ANSI escape
    sequences are stripped before matching, even with -e or -i).

    With --wait, polls the screen once per second until a match is found or
    the timeout expires. Exits with status 1 if no match is found.

    \b
    Examples:
      mockterm grep "ready"
      mockterm grep --wait -t 30 "server started"
      mockterm grep -B2 -A2 "error"
      mockterm grep -i "error"
    """
    if image and escape_codes:
        raise click.UsageError("--image and --escape-codes are mutually exclusive")

    tmux_session = require_tmux_session(session_id)

    # Resolve -C into before/after
    if context:
        before = max(before, context)
        after = max(after, context)

    deadline = time.monotonic() + timeout if wait else None

    while True:
        # image mode always captures escape codes internally for colour rendering
        screen = capture_pane(tmux_session, escape_codes=escape_codes or image)
        lines = screen.splitlines()
        indices = _grep_indices(lines, pattern, before, after)

        if indices:
            if image:
                print(_render_and_save(lines, indices, "grep", session_id))
            elif escape_codes:
                print("\n".join(sanitize_sgr_slice(lines, indices)))
            else:
                print("\n".join(lines[i] for i in indices))
            sys.exit(0)

        if deadline is None or time.monotonic() >= deadline:
            break

        time.sleep(1.0)

    # No match found
    sys.exit(1)


def _grep_indices(lines: list[str], pattern: str, before: int, after: int) -> list[int]:
    """Return sorted indices of lines matching pattern, plus before/after context lines.

    Pattern is matched against visible text (SGR sequences stripped) so that
    colour codes do not interfere with the search.
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise SystemExit(f"mockterm: invalid pattern: {e}") from e

    n = len(lines)
    included: set[int] = set()
    for i, line in enumerate(lines):
        if regex.search(strip_sgr(line)):
            for j in range(max(0, i - before), min(n, i + after + 1)):
                included.add(j)

    return sorted(included)


# ---------------------------------------------------------------------------
# send-keys
# ---------------------------------------------------------------------------


@main.command("send-keys")
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
@click.argument("keys", nargs=-1, required=True)
def send_keys(session_id: str, keys: tuple[str, ...]) -> None:
    """Send keys or key names to the terminal session.

    Key names follow tmux conventions: Enter, Escape, C-c, Tab, Up, Down, etc.
    String arguments are sent as literal text.

    \b
    Examples:
      mockterm send-keys "ls -la" Enter
      mockterm send-keys C-c
      mockterm send-keys Escape ":q!" Enter
    """
    import subprocess

    tmux_session = require_tmux_session(session_id)
    subprocess.run(
        ["tmux", "send-keys", "-t", tmux_session, *keys],
        check=True,
    )


# ---------------------------------------------------------------------------
# cat / head / tail
# ---------------------------------------------------------------------------


def _render_and_save(all_lines: list[str], selected: list[int], command: str, session_id: str) -> str:
    # Imported lazily so PIL is not loaded when --image is not used.
    from mockterm.render import render_and_save

    return render_and_save(all_lines, selected, command, session_id)


def _output_screen(
    session_id: str,
    escape_codes: bool,
    n_lines: int | None,
    from_end: bool,
    image: bool = False,
    command_name: str = "cat",
) -> None:
    """Shared implementation for cat, head, and tail."""
    tmux_session = require_tmux_session(session_id)
    screen = capture_pane(tmux_session, escape_codes=escape_codes or image)
    lines = screen.splitlines()

    total = len(lines)
    if n_lines is None:
        selected = list(range(total))
    elif from_end:
        selected = list(range(max(0, total - n_lines), total))
    else:
        selected = list(range(min(n_lines, total)))

    if image:
        print(_render_and_save(lines, selected, command_name, session_id))
    elif escape_codes:
        print("\n".join(sanitize_sgr_slice(lines, selected)))
    else:
        print("\n".join(lines[i] for i in selected))


_IMAGE_OPTION = click.option(
    "-i",
    "--image",
    is_flag=True,
    default=False,
    help="Render output as a PNG and print the file path.",
)

_ESCAPE_OPTION = click.option(
    "-e",
    "--escape-codes",
    is_flag=True,
    default=False,
    help="Preserve ANSI escape codes in output.",
)


@main.command()
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
@_ESCAPE_OPTION
@_IMAGE_OPTION
def cat(session_id: str, escape_codes: bool, image: bool) -> None:
    """Print the full current screen contents."""
    if image and escape_codes:
        raise click.UsageError("--image and --escape-codes are mutually exclusive")
    _output_screen(session_id, escape_codes, None, False, image, "cat")


@main.command()
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
@click.option("-n", "n_lines", type=int, default=10, show_default=True, help="Number of lines to print.")
@_ESCAPE_OPTION
@_IMAGE_OPTION
def head(session_id: str, n_lines: int, escape_codes: bool, image: bool) -> None:
    """Print the first N lines of the current screen."""
    if image and escape_codes:
        raise click.UsageError("--image and --escape-codes are mutually exclusive")
    _output_screen(session_id, escape_codes, n_lines, False, image, "head")


@main.command()
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
@click.option("-n", "n_lines", type=int, default=10, show_default=True, help="Number of lines to print.")
@_ESCAPE_OPTION
@_IMAGE_OPTION
def tail(session_id: str, n_lines: int, escape_codes: bool, image: bool) -> None:
    """Print the last N lines of the current screen."""
    if image and escape_codes:
        raise click.UsageError("--image and --escape-codes are mutually exclusive")
    _output_screen(session_id, escape_codes, n_lines, True, image, "tail")


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------


@main.command()
@click.option("-s", "--session", "session_id", default=DEFAULT_ID, show_default=True, help="Session ID.")
def kill(session_id: str) -> None:
    """Kill a running session and remove it from .mockterm."""
    kill_session(session_id)
    click.echo(f"Killed session '{session_id}'.")
