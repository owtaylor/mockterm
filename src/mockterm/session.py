"""
Session state management for mockterm.

Sessions are stored in a .mockterm INI file in the current directory.
Each section corresponds to a named session, keyed by session ID.
The tmux session name is stored as 'tmux_session' within each section.
"""

import configparser
import secrets
import subprocess
from pathlib import Path

STATE_FILE = ".mockterm"
DEFAULT_ID = "default"


def _state_path() -> Path:
    return Path(STATE_FILE)


def _read_state() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    path = _state_path()
    if path.exists():
        cfg.read(path)
    return cfg


def _write_state(cfg: configparser.ConfigParser) -> None:
    with open(_state_path(), "w") as f:
        cfg.write(f)


def _tmux_session_name(session_id: str) -> str:
    """Build a unique tmux session name from a mockterm session ID.

    The random tag ensures two agents working in different directories
    with the same logical session ID don't collide in tmux's namespace.
    """
    tag = secrets.token_hex(3)  # 6 hex chars, e.g. "a3f9c1"
    return f"mockterm-{session_id}-{tag}"


def get_tmux_session(session_id: str) -> str | None:
    """Return the tmux session name for a mockterm session, or None if not found."""
    cfg = _read_state()
    if cfg.has_section(session_id):
        return cfg[session_id].get("tmux_session")
    return None


def tmux_session_exists(tmux_session: str) -> bool:
    """Return True if a tmux session with the given name currently exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
    )
    return result.returncode == 0


def kill_session(session_id: str) -> None:
    """Kill the tmux session associated with session_id (if any) and remove its state."""
    cfg = _read_state()
    if cfg.has_section(session_id):
        tmux_session = cfg[session_id].get("tmux_session")
        if tmux_session and tmux_session_exists(tmux_session):
            subprocess.run(
                ["tmux", "kill-session", "-t", tmux_session],
                capture_output=True,
            )
        cfg.remove_section(session_id)
        _write_state(cfg)


def start_session(session_id: str, command: list[str], cols: int, rows: int) -> str:
    """
    Start a new tmux session running command, recording it in .mockterm.

    Kills any existing session with the same ID first.
    Returns the tmux session name.
    """
    kill_session(session_id)

    tmux_session = _tmux_session_name(session_id)

    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",  # detached
            "-s",
            tmux_session,
            "-x",
            str(cols),
            "-y",
            str(rows),
            "--",
            *command,
        ],
        check=True,
    )

    cfg = _read_state()
    if not cfg.has_section(session_id):
        cfg.add_section(session_id)
    cfg[session_id]["tmux_session"] = tmux_session
    _write_state(cfg)

    return tmux_session


def require_tmux_session(session_id: str) -> str:
    """
    Return the tmux session name for session_id, raising SystemExit if not found.
    """
    tmux_session = get_tmux_session(session_id)
    if tmux_session is None:
        raise SystemExit(f"mockterm: no session '{session_id}' found in {STATE_FILE}. Run 'mockterm start' first.")
    if not tmux_session_exists(tmux_session):
        raise SystemExit(
            f"mockterm: tmux session '{tmux_session}' no longer exists. Run 'mockterm start' to create a new session."
        )
    return tmux_session


def capture_pane(tmux_session: str, *, escape_codes: bool = False) -> str:
    """
    Capture the current screen contents of a tmux pane.

    Returns the screen as a string. By default, strips ANSI escape sequences.
    Pass escape_codes=True to preserve them.
    """
    cmd = ["tmux", "capture-pane", "-p", "-t", tmux_session]
    if escape_codes:
        cmd.append("-e")

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout
