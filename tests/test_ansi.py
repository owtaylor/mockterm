"""Unit tests for mockterm.ansi (no tmux needed)."""

from mockterm.ansi import SgrState, apply_sgr, sanitize_sgr_slice, strip_sgr


class TestSgrState:
    def test_default_state(self) -> None:
        s = SgrState()
        assert s.is_default()
        assert s.as_escape() == "\033[0m"

    def test_apply_fg_colour(self) -> None:
        s = SgrState()
        apply_sgr(s, "31")
        assert s.fg == 31
        assert not s.is_default()
        esc = s.as_escape()
        assert "31" in esc
        assert esc.startswith("\033[0;")

    def test_apply_spanning_reset(self) -> None:
        s = SgrState()
        apply_sgr(s, "94")
        assert s.fg == 94
        apply_sgr(s, "0")
        assert s.is_default()

    def test_apply_256_colour(self) -> None:
        s = SgrState()
        apply_sgr(s, "38;5;200")
        assert s.fg == (38, 5, 200)
        assert not s.is_default()

    def test_apply_24bit_colour(self) -> None:
        s = SgrState()
        apply_sgr(s, "38;2;10;20;30")
        assert s.fg == (38, 2, 10, 20, 30)

    def test_apply_bg_colour(self) -> None:
        s = SgrState()
        apply_sgr(s, "44")
        assert s.bg == 44

    def test_apply_bold(self) -> None:
        s = SgrState()
        apply_sgr(s, "1")
        assert s.bold
        apply_sgr(s, "22")
        assert not s.bold

    def test_apply_multiple_params(self) -> None:
        s = SgrState()
        # Bold + red fg + blue bg in one sequence
        apply_sgr(s, "1;31;44")
        assert s.bold
        assert s.fg == 31
        assert s.bg == 44

    def test_equality(self) -> None:
        s1 = SgrState()
        s2 = SgrState()
        assert s1 == s2
        apply_sgr(s1, "31")
        assert s1 != s2
        apply_sgr(s2, "31")
        assert s1 == s2

    def test_strip_sgr(self) -> None:
        line = "\033[94m~\033[39mtext\033[94m"
        assert strip_sgr(line) == "~text"

    def test_strip_sgr_no_codes(self) -> None:
        line = "plain text"
        assert strip_sgr(line) == "plain text"


class TestSanitizeSgrSlice:
    LINES = [
        "\033[94m~",
        "\033[39mFOO\033[94m",
        "normal",
    ]

    def test_empty_selection(self) -> None:
        assert sanitize_sgr_slice(self.LINES, []) == []

    def test_full_selection_ends_with_reset(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [0, 1, 2])
        joined = "".join(result)
        assert joined.endswith("\033[0m")

    def test_full_selection_no_spurious_prefix_on_line0(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [0, 1, 2])
        assert result[0] == self.LINES[0]
        assert result[-1].endswith("\033[0m")

    def test_tail_prefixes_correct_state(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [1, 2])
        assert result[0].startswith("\033[0;94m")

    def test_tail_ends_with_reset(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [1, 2])
        joined = "".join(result)
        assert joined.endswith("\033[0m")

    def test_coloured_context_line_prefixed(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [2])
        assert result[0].startswith("\033[0;94m")
        assert result[0].endswith("\033[0m")

    def test_grep_match_on_coloured_line(self) -> None:
        result = sanitize_sgr_slice(self.LINES, [1])
        assert result[0].startswith("\033[0;94m")
        assert result[0].endswith("\033[0m")

    def test_no_double_reset(self) -> None:
        lines = ["\033[31mRED\033[0m"]
        result = sanitize_sgr_slice(lines, [0])
        assert result[0].count("\033[0m") == 1

    def test_no_reset_when_already_default(self) -> None:
        lines = ["\033[31mRED\033[39m", "plain"]
        result = sanitize_sgr_slice(lines, [0, 1])
        joined = "".join(result)
        assert not joined.endswith("\033[0m")
