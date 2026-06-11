"""Unit tests for mockterm.render (no tmux required)."""

from pathlib import Path
from unittest.mock import patch

import pytest

import mockterm.render as render_mod
from mockterm.render import (
    DEFAULT_BG,
    DEFAULT_FG,
    ansi256_to_rgb,
    find_font_family,
    render_lines,
    resolve_color,
    save_screenshot,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _reset_font_cache() -> None:
    """Force find_font_family() to re-run its search on next call."""
    render_mod._font_searched = False
    render_mod._cached_family = None


# ---------------------------------------------------------------------------
# ansi256_to_rgb
# ---------------------------------------------------------------------------


class TestAnsi256ToRgb:
    def test_basic_black(self) -> None:
        # index 0 is pure black (Color0 follows system theme in Ptyxis)
        assert ansi256_to_rgb(0) == (0, 0, 0)

    def test_basic_white(self) -> None:
        assert ansi256_to_rgb(15) == (246, 245, 244)

    def test_cube_start(self) -> None:
        assert ansi256_to_rgb(16) == (0, 0, 0)

    def test_cube_bright_red(self) -> None:
        assert ansi256_to_rgb(196) == (255, 0, 0)

    def test_cube_white(self) -> None:
        assert ansi256_to_rgb(231) == (255, 255, 255)

    def test_grayscale_start(self) -> None:
        assert ansi256_to_rgb(232) == (8, 8, 8)

    def test_grayscale_end(self) -> None:
        assert ansi256_to_rgb(255) == (238, 238, 238)

    def test_grayscale_is_grey(self) -> None:
        r, g, b = ansi256_to_rgb(240)
        assert r == g == b


# ---------------------------------------------------------------------------
# resolve_color
# ---------------------------------------------------------------------------


class TestResolveColor:
    def test_none_returns_default(self) -> None:
        assert resolve_color(None, DEFAULT_FG) == DEFAULT_FG

    def test_named_red(self) -> None:
        assert resolve_color(31, DEFAULT_FG) == (192, 28, 40)

    def test_named_bright_red(self) -> None:
        assert resolve_color(91, DEFAULT_FG) == (237, 51, 59)

    def test_bold_does_not_affect_colour(self) -> None:
        # bold selects a heavier font face but must not shift named colours to bright
        assert resolve_color(31, DEFAULT_FG) == (192, 28, 40)

    def test_default_fg_code(self) -> None:
        assert resolve_color(39, DEFAULT_FG) == DEFAULT_FG

    def test_bg_black(self) -> None:
        assert resolve_color(40, DEFAULT_BG) == (0, 0, 0)

    def test_bg_bright_white(self) -> None:
        assert resolve_color(107, DEFAULT_BG) == (246, 245, 244)

    def test_default_bg_code(self) -> None:
        assert resolve_color(49, DEFAULT_BG) == DEFAULT_BG

    def test_256_colour(self) -> None:
        assert resolve_color((38, 5, 196), DEFAULT_FG) == (255, 0, 0)

    def test_24bit_colour(self) -> None:
        assert resolve_color((38, 2, 255, 128, 0), DEFAULT_FG) == (255, 128, 0)

    def test_unknown_tuple_returns_default(self) -> None:
        assert resolve_color((99,), DEFAULT_FG) == DEFAULT_FG


# ---------------------------------------------------------------------------
# find_font_family (mocked)
# ---------------------------------------------------------------------------


class TestFindFontFamily:
    def setup_method(self) -> None:
        _reset_font_cache()

    def teardown_method(self) -> None:
        _reset_font_cache()

    def test_returns_none_when_nothing_found(self) -> None:
        with (
            patch("mockterm.render._fc_list", return_value=[]),
            patch("mockterm.render._find_in_dirs", return_value=None),
        ):
            result = find_font_family()
        assert result is None

    def test_uses_fc_list_path(self, tmp_path: Path) -> None:
        # All four variants must be present for a family to be accepted.
        fake_files = {
            "DejaVuSansMono.ttf": tmp_path / "DejaVuSansMono.ttf",
            "DejaVuSansMono-Bold.ttf": tmp_path / "DejaVuSansMono-Bold.ttf",
            "DejaVuSansMono-Oblique.ttf": tmp_path / "DejaVuSansMono-Oblique.ttf",
            "DejaVuSansMono-BoldOblique.ttf": tmp_path / "DejaVuSansMono-BoldOblique.ttf",
        }
        for p in fake_files.values():
            p.touch()

        def _fake_fc(family: str) -> list[Path]:
            return list(fake_files.values()) if "DejaVu" in family else []

        with (
            patch("mockterm.render._fc_list", side_effect=_fake_fc),
            patch("mockterm.render._find_in_dirs", return_value=None),
        ):
            result = find_font_family()
        assert result is not None
        assert result.regular == fake_files["DejaVuSansMono.ttf"]
        assert result.bold == fake_files["DejaVuSansMono-Bold.ttf"]

    def test_falls_back_to_dir_scan_when_fc_list_absent(self, tmp_path: Path) -> None:
        # Directory fallback is triggered only when fc-list binary is missing.
        fake_files = {
            "DejaVuSansMono.ttf": tmp_path / "DejaVuSansMono.ttf",
            "DejaVuSansMono-Bold.ttf": tmp_path / "DejaVuSansMono-Bold.ttf",
            "DejaVuSansMono-Oblique.ttf": tmp_path / "DejaVuSansMono-Oblique.ttf",
            "DejaVuSansMono-BoldOblique.ttf": tmp_path / "DejaVuSansMono-BoldOblique.ttf",
        }
        for p in fake_files.values():
            p.touch()

        def _fake_find(fname: str) -> Path | None:
            return fake_files.get(fname)

        with (
            patch("mockterm.render._fc_list", side_effect=FileNotFoundError),
            patch("mockterm.render._find_in_dirs", side_effect=_fake_find),
        ):
            result = find_font_family()
        assert result is not None
        assert result.regular == fake_files["DejaVuSansMono.ttf"]

    def test_fc_list_available_does_not_fall_back_to_dirs(self) -> None:
        # When fc-list is available but finds nothing, we do NOT search directories.
        with (
            patch("mockterm.render._fc_list", return_value=[]),
            patch("mockterm.render._find_in_dirs") as mock_find,
        ):
            result = find_font_family()
        assert result is None
        mock_find.assert_not_called()

    def test_result_is_cached(self, tmp_path: Path) -> None:
        fake_files = {
            "DejaVuSansMono.ttf": tmp_path / "DejaVuSansMono.ttf",
            "DejaVuSansMono-Bold.ttf": tmp_path / "DejaVuSansMono-Bold.ttf",
            "DejaVuSansMono-Oblique.ttf": tmp_path / "DejaVuSansMono-Oblique.ttf",
            "DejaVuSansMono-BoldOblique.ttf": tmp_path / "DejaVuSansMono-BoldOblique.ttf",
        }
        for p in fake_files.values():
            p.touch()

        call_count = 0

        def _fake_fc(family: str) -> list[Path]:
            nonlocal call_count
            call_count += 1
            return list(fake_files.values()) if "DejaVu" in family else []

        with (
            patch("mockterm.render._fc_list", side_effect=_fake_fc),
            patch("mockterm.render._find_in_dirs", return_value=None),
        ):
            find_font_family()
            find_font_family()
        assert call_count == 1  # second call uses cache


# ---------------------------------------------------------------------------
# render_lines + save_screenshot (require actual fonts)
# ---------------------------------------------------------------------------


class TestRenderLines:
    def test_plain_text_dimensions(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        lines = ["Hello world"]
        img = render_lines(lines, [0], fonts)

        expected_w = len("Hello world") * fonts.cell_w
        assert img.size == (expected_w, fonts.cell_h)

    def test_trailing_whitespace_trimmed(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        lines = ["Hi" + " " * 50]
        img = render_lines(lines, [0], fonts)

        assert img.size[0] == 2 * fonts.cell_w

    def test_coloured_fg_affects_pixel(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        # Red background cell should produce red pixels
        lines = ["\x1b[41m \x1b[0m"]  # space on red background
        img = render_lines(lines, [0], fonts)

        # The only rendered cell is a space on red bg – check at least one pixel is reddish
        red_pixels = [
            img.getpixel((x, y))
            for x in range(img.width)
            for y in range(img.height)
            if img.getpixel((x, y))[0] > 100 and img.getpixel((x, y))[1] < 50  # type: ignore[index]
        ]
        assert len(red_pixels) > 0

    def test_empty_selection_gives_single_cell(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        img = render_lines([], [], fonts)
        assert img.size == (fonts.cell_w, fonts.cell_h)

    def test_multiline_height(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        lines = ["line one", "line two", "line three"]
        img = render_lines(lines, [0, 1, 2], fonts)
        assert img.size[1] == 3 * fonts.cell_h

    def test_selected_subset_of_lines(self) -> None:
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        lines = ["line one", "line two", "line three"]
        img = render_lines(lines, [1], fonts)
        assert img.size[1] == fonts.cell_h


class TestSaveScreenshot:
    def test_creates_directory_and_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        img = render_lines(["hello"], [0], fonts)
        path = save_screenshot(img, "cat", "default", "hello")

        assert path.exists()
        assert path.suffix == ".png"
        assert path.stat().st_size > 0
        assert "cat" in path.name
        assert "default" in path.name

    def test_path_is_absolute(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        from mockterm.render import DEFAULT_FONT_SIZE, load_fonts

        family = find_font_family()
        assert family is not None
        fonts = load_fonts(family, DEFAULT_FONT_SIZE)

        img = render_lines(["hello"], [0], fonts)
        path = save_screenshot(img, "head", "mysession", "hello")

        assert path.is_absolute()
