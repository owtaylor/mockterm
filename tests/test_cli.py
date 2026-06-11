"""
Integration tests for mockterm.

These tests exercise the CLI end-to-end via the Click test runner and real tmux
sessions.  Each test runs in a temporary directory so that .mockterm files are
isolated from one another.
"""

import time
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from click.testing import CliRunner

from mockterm.cli import main


@pytest.fixture()
def invoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., tuple[int, str]]:
    """Return a callable that invokes the CLI in a fresh temp directory.

    Usage::

        def test_foo(invoke):
            code, out = invoke("start", "sleep", "60")
    """
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    def _invoke(*args: str) -> tuple[int, str]:
        result = runner.invoke(main, list(args))
        return result.exit_code, result.output

    return _invoke


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_creates_session(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        code, out = invoke("start", "echo", "hello")
        assert code == 0
        assert "Started session 'default'" in out
        assert (tmp_path / ".mockterm").exists()

    def test_start_writes_ini(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        invoke("start", "echo", "hello")
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(tmp_path / ".mockterm")
        assert cfg.has_section("default")
        assert "tmux_session" in cfg["default"]

    def test_start_replaces_existing_session(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code1, _ = invoke("start", "sleep", "60")
        assert code1 == 0
        code2, out2 = invoke("start", "sleep", "60")
        assert code2 == 0
        assert "Started session 'default'" in out2

    def test_start_named_session(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        code, out = invoke("start", "-s", "myapp", "sleep", "60")
        assert code == 0
        assert "Started session 'myapp'" in out
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(tmp_path / ".mockterm")
        assert cfg.has_section("myapp")

    def test_multiple_named_sessions_coexist(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        invoke("start", "-s", "a", "sleep", "60")
        invoke("start", "-s", "b", "sleep", "60")
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(tmp_path / ".mockterm")
        assert cfg.has_section("a")
        assert cfg.has_section("b")

    def test_start_custom_size(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("start", "--size", "80x24", "sleep", "60")
        assert code == 0
        assert "80x24" in out

    def test_start_invalid_size(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("start", "--size", "badsize", "sleep", "60")
        assert code != 0

    def teardown_method(self) -> None:  # best-effort cleanup
        import subprocess

        subprocess.run(
            ["tmux", "kill-server"],
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# cat / head / tail
# ---------------------------------------------------------------------------


class TestCatHeadTail:
    @pytest.fixture(autouse=True)
    def _start_session(self, invoke: Callable[..., tuple[int, str]]) -> None:
        """Start a session running 'printf' to produce known output."""
        # Print 20 numbered lines and then sleep so the session stays alive
        invoke(
            "start",
            "bash",
            "-c",
            'for i in $(seq 1 20); do echo "line $i"; done; sleep 60',
        )
        # Give the command a moment to run
        time.sleep(0.3)

    def test_cat_returns_content(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("cat")
        assert code == 0
        assert "line 1" in out

    def test_head_returns_first_lines(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("head", "-n", "3")
        assert code == 0
        lines = [line for line in out.splitlines() if line.strip()]
        assert len(lines) <= 3

    def test_tail_returns_last_lines(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("tail", "-n", "3")
        assert code == 0
        lines = [line for line in out.splitlines() if line.strip()]
        assert len(lines) <= 3

    def test_cat_no_session_exits_nonzero(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, _ = invoke("cat", "-s", "nonexistent")
        assert code != 0

    def teardown_method(self) -> None:
        import subprocess

        subprocess.run(["tmux", "kill-server"], capture_output=True)


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class TestGrep:
    @pytest.fixture(autouse=True)
    def _start_session(self, invoke: Callable[..., tuple[int, str]]) -> None:
        invoke(
            "start",
            "bash",
            "-c",
            "echo 'hello world'; echo 'foo bar'; echo 'baz'; sleep 60",
        )
        time.sleep(0.3)

    def test_grep_finds_pattern(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "hello")
        assert code == 0
        assert "hello world" in out

    def test_grep_no_match_exits_1(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, _ = invoke("grep", "zzznomatch")
        assert code == 1

    def test_grep_context_before(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "-B", "1", "foo")
        assert code == 0
        assert "hello world" in out  # line before "foo bar"
        assert "foo bar" in out

    def test_grep_context_after(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "-A", "1", "foo")
        assert code == 0
        assert "foo bar" in out
        assert "baz" in out

    def test_grep_context_C(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "-C", "1", "foo")
        assert code == 0
        assert "hello world" in out
        assert "foo bar" in out
        assert "baz" in out

    def test_grep_wait_finds_delayed_output(self, invoke: Callable[..., tuple[int, str]]) -> None:
        """--wait should poll until the pattern appears."""
        # Restart the session with a deliberate delay before printing the key string
        invoke("kill")
        invoke(
            "start",
            "bash",
            "-c",
            "sleep 1.5; echo 'ready'; sleep 60",
        )
        code, out = invoke("grep", "--wait", "-t", "10", "ready")
        assert code == 0
        assert "ready" in out

    def test_grep_wait_timeout_exits_1(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, _ = invoke("grep", "--wait", "-t", "2", "zzznomatch")
        assert code == 1

    def teardown_method(self) -> None:
        import subprocess

        subprocess.run(["tmux", "kill-server"], capture_output=True)


# ---------------------------------------------------------------------------
# send-keys
# ---------------------------------------------------------------------------


class TestSendKeys:
    @pytest.fixture(autouse=True)
    def _start_session(self, invoke: Callable[..., tuple[int, str]]) -> None:
        # Start bash interactively (no prompt noise from PS1)
        invoke("start", "bash", "--norc", "--noprofile")
        time.sleep(0.3)

    def test_send_keys_and_read_output(self, invoke: Callable[..., tuple[int, str]]) -> None:
        invoke("send-keys", "echo greetings", "Enter")
        time.sleep(0.3)
        code, out = invoke("grep", "greetings")
        assert code == 0
        assert "greetings" in out

    def test_send_ctrl_c(self, invoke: Callable[..., tuple[int, str]]) -> None:
        """Sending C-c should not crash."""
        code, _ = invoke("send-keys", "C-c")
        assert code == 0

    def teardown_method(self) -> None:
        import subprocess

        subprocess.run(["tmux", "kill-server"], capture_output=True)


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------


class TestKill:
    def test_kill_removes_section(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        invoke("start", "sleep", "60")
        code, out = invoke("kill")
        assert code == 0
        assert "Killed" in out
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(tmp_path / ".mockterm")
        assert not cfg.has_section("default")

    def test_kill_named_session(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> None:
        invoke("start", "-s", "myapp", "sleep", "60")
        invoke("start", "-s", "other", "sleep", "60")
        invoke("kill", "-s", "myapp")
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(tmp_path / ".mockterm")
        assert not cfg.has_section("myapp")
        assert cfg.has_section("other")

    def teardown_method(self) -> None:
        import subprocess

        subprocess.run(["tmux", "kill-server"], capture_output=True)


# ---------------------------------------------------------------------------
# Integration: escape-code sanitization through the CLI
# ---------------------------------------------------------------------------


class TestEscapeCodesSanitized:
    """Integration tests that verify -e output is self-contained.

    We simulate the vi welcome screen, which has been observed to cause tmux
    to generate lines ending with open SGR attributes — exactly the leak
    pattern that _sanitize_sgr_slice must close.
    """

    # Terminal width must match the mockterm default (DEFAULT_COLS = 120).
    _COLS = 120

    @classmethod
    def _make_sgr_content(cls) -> str:
        """Build synthetic vi-style content with full-width padded lines."""
        cols = cls._COLS

        def tilde_line() -> str:
            # Entire line in bright-cyan; trailing spaces keep the colour active.
            return "\033[94m~" + " " * (cols - 1) + "\n"

        def content_line(text: str, indent: int = 40) -> str:
            # ~ + indent spaces in bright-cyan, then text in default fg, then
            # back to bright-cyan to fill to column width.
            return (
                "\033[94m~"
                + " " * (indent - 1)
                + "\033[39m"
                + text
                + "\033[94m"
                + " " * max(0, cols - indent - len(text))
                + "\n"
            )

        return (
            tilde_line()
            + content_line("Author: Vim Team")
            + content_line("type  :q<Enter>  to exit")
            + tilde_line() * 3
        )

    @pytest.fixture(autouse=True)
    def _start_session(self, invoke: Callable[..., tuple[int, str]], tmp_path: Path) -> Generator:
        output_file = tmp_path / "sgr_output.txt"
        output_file.write_text(self._make_sgr_content())
        invoke("start", "-s", "vi-sgr", "sh", "-c", f"cat {output_file} && sleep 3600")
        time.sleep(0.5)
        yield
        invoke("kill", "-s", "vi-sgr")

    def test_cat_e_ends_with_reset(self, invoke: Callable[..., tuple[int, str]]) -> None:
        _, out = invoke("cat", "-e", "-s", "vi-sgr")
        assert out.rstrip("\n").endswith("\033[0m")

    def test_grep_e_author_ends_with_reset(self, invoke: Callable[..., tuple[int, str]]) -> None:
        """The original bug: grep -e on a coloured line leaked an open SGR code."""
        _, out = invoke("grep", "-e", "-s", "vi-sgr", "Author")
        assert "Author" in out
        assert out.rstrip("\n").endswith("\033[0m")

    def test_grep_e_matches_visible_text_not_codes(self, invoke: Callable[..., tuple[int, str]]) -> None:
        # '94' appears in escape codes in the output; grep should NOT match it.
        code, _ = invoke("grep", "-e", "-s", "vi-sgr", r"^\d+$")
        assert code == 1  # no line whose visible text is purely digits


# ---------------------------------------------------------------------------
# Integration: --image flag
# ---------------------------------------------------------------------------


class TestImage:
    """Verify that --image writes a PNG and prints its absolute path."""

    @pytest.fixture(autouse=True)
    def _start_session(self, invoke: Callable[..., tuple[int, str]]) -> Generator:
        invoke("start", "-s", "img", "sh", "-c", "printf '\\033[32mHello\\033[0m world\\n'; sleep 3600")
        time.sleep(0.5)
        yield
        invoke("kill", "-s", "img")

    def test_cat_image_outputs_path(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("cat", "-i", "-s", "img")
        assert code == 0
        path = Path(out.strip())
        assert path.is_absolute()
        assert path.suffix == ".png"
        assert path.exists()
        assert path.stat().st_size > 0

    def test_head_image_outputs_path(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("head", "-n", "5", "-i", "-s", "img")
        assert code == 0
        path = Path(out.strip())
        assert path.exists() and path.suffix == ".png"

    def test_tail_image_outputs_path(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("tail", "-n", "3", "-i", "-s", "img")
        assert code == 0
        path = Path(out.strip())
        assert path.exists() and path.suffix == ".png"

    def test_grep_image_outputs_path(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "-i", "-s", "img", "Hello")
        assert code == 0
        path = Path(out.strip())
        assert path.exists() and path.suffix == ".png"

    def test_image_filename_contains_command_and_session(self, invoke: Callable[..., tuple[int, str]]) -> None:
        _, out = invoke("cat", "-i", "-s", "img")
        name = Path(out.strip()).name
        assert "cat" in name
        assert "img" in name

    def test_image_and_escape_codes_are_exclusive(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("cat", "-i", "-e", "-s", "img")
        assert code != 0
        assert "mutually exclusive" in out

    def test_image_and_escape_codes_exclusive_grep(self, invoke: Callable[..., tuple[int, str]]) -> None:
        code, out = invoke("grep", "-i", "-e", "-s", "img", "Hello")
        assert code != 0
        assert "mutually exclusive" in out
