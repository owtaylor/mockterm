"""Terminal screenshot rendering: ANSI-coloured text → PNG image."""

import copy
import math
import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mockterm.ansi import SGR_RE, SgrState, apply_sgr, sanitize_sgr_slice, strip_sgr

# ─── constants ───────────────────────────────────────────────────────────────

DEFAULT_FONT_SIZE: int = 20


def effective_font_size() -> int:
    """Return the font size to use, allowing override via MOCKTERM_FONT_SIZE env var."""
    try:
        return int(os.environ["MOCKTERM_FONT_SIZE"])
    except KeyError:
        return DEFAULT_FONT_SIZE
    except ValueError:
        return DEFAULT_FONT_SIZE


# https://gitlab.gnome.org/chergert/ptyxis/-/blob/main/src/palettes/gnome.palette
DEFAULT_FG: tuple[int, int, int] = (192, 191, 188)  # Color7  #c0bfbc
DEFAULT_BG: tuple[int, int, int] = (0, 0, 0)  # black (Color0 follows system theme in Ptyxis)

# GNOME Ptyxis 16-colour palette: indices 0-7 normal, 8-15 bright
_ANSI16: list[tuple[int, int, int]] = [
    (0, 0, 0),  # 0  black (system theme in Ptyxis, use pure black)
    (192, 28, 40),  # 1  #c01c28  red
    (46, 194, 126),  # 2  #2ec27e  green
    (245, 194, 17),  # 3  #f5c211  yellow
    (30, 120, 228),  # 4  #1e78e4  blue
    (152, 65, 187),  # 5  #9841bb  magenta
    (10, 185, 220),  # 6  #0ab9dc  cyan
    (192, 191, 188),  # 7  #c0bfbc  white
    (94, 92, 100),  # 8  #5e5c64  bright black
    (237, 51, 59),  # 9  #ed333b  bright red
    (87, 227, 137),  # 10  #57e389  bright green
    (248, 228, 92),  # 11  #f8e45c  bright yellow
    (81, 161, 255),  # 12  #51a1ff  bright blue
    (192, 97, 203),  # 13  #c061cb  bright magenta
    (79, 210, 253),  # 14  #4fd2fd  bright cyan
    (246, 245, 244),  # 15  #f6f5f4  bright white
]

# ─── font discovery ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FontFamily:
    regular: Path
    bold: Path
    oblique: Path  # italic / oblique
    bold_oblique: Path  # bold italic / bold oblique


# Priority-ordered list of (fc_family_name, regular, bold, oblique, bold_oblique)
_CANDIDATES: list[tuple[str, str, str, str, str]] = [
    (
        "DejaVu Sans Mono",
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Bold.ttf",
        "DejaVuSansMono-Oblique.ttf",
        "DejaVuSansMono-BoldOblique.ttf",
    ),
    (
        "Liberation Mono",
        "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf",
        "LiberationMono-Italic.ttf",
        "LiberationMono-BoldItalic.ttf",
    ),
]

_SEARCH_DIRS: list[Path] = [
    # Ubuntu / Debian
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    # Fedora / RHEL
    Path("/usr/share/fonts/dejavu-sans-mono-fonts"),
    Path("/usr/share/fonts/dejavu"),
    Path("/usr/share/fonts/liberation-mono"),
    # Generic catch-all (shallow search only)
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
]


def _fc_list(family: str) -> list[Path]:
    """Return font file paths for *family* via fc-list.

    Raises FileNotFoundError if the fc-list binary is not installed (allowing
    the caller to fall back to directory search).  Returns [] if fc-list is
    available but the family is not found.
    """
    try:
        result = subprocess.run(
            ["fc-list", f":family={family}", "--format", "%{file}\n"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return []
    # FileNotFoundError is not caught here: it propagates to signal that
    # fc-list is absent and the caller should use directory search instead.
    return [Path(p) for p in result.stdout.splitlines() if p.strip()]


def _find_in_dirs(filename: str) -> Path | None:
    """Search known font directories for *filename*."""
    for d in _SEARCH_DIRS:
        p = d / filename
        if p.is_file():
            return p
        if d.is_dir():
            for sub in d.iterdir():
                if sub.is_dir():
                    p2 = sub / filename
                    if p2.is_file():
                        return p2
    return None


_font_searched: bool = False
_cached_family: FontFamily | None = None


def find_font_family() -> FontFamily | None:
    """Return the first available monospace FontFamily, or None.

    Uses fc-list when available (preferred: faster, distro-agnostic).  If
    fc-list is not installed, falls back to scanning known directory paths.
    In both cases all four style variants (regular, bold, oblique, bold
    oblique) must be present; partial installs are skipped.
    """
    global _font_searched, _cached_family
    if _font_searched:
        return _cached_family

    _font_searched = True

    try:
        # fc-list is available: use it exclusively, do not search directories.
        for fc_family, reg, bold, oblique, boldoblique in _CANDIDATES:
            fc_files = _fc_list(fc_family)  # raises FileNotFoundError if binary absent
            by_name: dict[str, Path] = {p.name: p for p in fc_files}
            regular = by_name.get(reg)
            bold_p = by_name.get(bold)
            oblique_p = by_name.get(oblique)
            boldoblique_p = by_name.get(boldoblique)
            if regular and bold_p and oblique_p and boldoblique_p:
                _cached_family = FontFamily(regular, bold_p, oblique_p, boldoblique_p)
                return _cached_family
    except FileNotFoundError:
        # fc-list binary not found; fall back to scanning known directories.
        for _, reg, bold, oblique, boldoblique in _CANDIDATES:
            regular = _find_in_dirs(reg)
            bold_p = _find_in_dirs(bold)
            oblique_p = _find_in_dirs(oblique)
            boldoblique_p = _find_in_dirs(boldoblique)
            if regular and bold_p and oblique_p and boldoblique_p:
                _cached_family = FontFamily(regular, bold_p, oblique_p, boldoblique_p)
                return _cached_family

    return None


# ─── loaded fonts ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoadedFonts:
    regular: ImageFont.FreeTypeFont
    bold: ImageFont.FreeTypeFont
    oblique: ImageFont.FreeTypeFont
    bold_oblique: ImageFont.FreeTypeFont
    cell_w: int
    cell_h: int
    ascent: int


def load_fonts(family: FontFamily, size: int = DEFAULT_FONT_SIZE) -> LoadedFonts:
    """Load all four font variants and compute monospace cell dimensions."""
    regular = ImageFont.truetype(str(family.regular), size)
    bold = ImageFont.truetype(str(family.bold), size)
    oblique = ImageFont.truetype(str(family.oblique), size)
    bold_oblique = ImageFont.truetype(str(family.bold_oblique), size)

    ascent, descent = regular.getmetrics()
    cell_h = ascent + descent
    cell_w = math.ceil(regular.getlength("M"))

    return LoadedFonts(
        regular=regular,
        bold=bold,
        oblique=oblique,
        bold_oblique=bold_oblique,
        cell_w=cell_w,
        cell_h=cell_h,
        ascent=ascent,
    )


# ─── colour resolution ───────────────────────────────────────────────────────


def ansi256_to_rgb(n: int) -> tuple[int, int, int]:
    """Convert an xterm 256-colour index to an RGB triple."""
    if n < 16:
        return _ANSI16[n]
    if n < 232:
        n -= 16
        b, n = n % 6, n // 6
        g, r = n % 6, n // 6

        def _v(x: int) -> int:
            return 0 if x == 0 else 55 + x * 40

        return (_v(r), _v(g), _v(b))
    val = 8 + (n - 232) * 10
    return (val, val, val)


def resolve_color(
    color: int | tuple[int, ...] | None,
    default: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Map an SgrState colour value to an RGB triple."""
    if color is None:
        return default
    if isinstance(color, tuple):
        if len(color) >= 3 and color[1] == 5:
            return ansi256_to_rgb(color[2])
        if len(color) >= 5 and color[1] == 2:
            return (color[2], color[3], color[4])
        return default
    # Named SGR colour code
    if 30 <= color <= 37:
        return _ANSI16[color - 30]
    if color == 39:
        return default
    if 40 <= color <= 47:
        return _ANSI16[color - 40]
    if color == 49:
        return default
    if 90 <= color <= 97:
        return _ANSI16[color - 90 + 8]
    if 100 <= color <= 107:
        return _ANSI16[color - 100 + 8]
    return default


# ─── renderer ────────────────────────────────────────────────────────────────


def _pick_font(fonts: LoadedFonts, bold: bool, italic: bool) -> ImageFont.FreeTypeFont:
    if bold and italic:
        return fonts.bold_oblique
    if bold:
        return fonts.bold
    if italic:
        return fonts.oblique
    return fonts.regular


def _render_char(
    draw: ImageDraw.ImageDraw,
    ch: str,
    x: int,
    y: int,
    state: SgrState,
    fonts: LoadedFonts,
) -> None:
    fg = resolve_color(state.fg, DEFAULT_FG)
    bg = resolve_color(state.bg, DEFAULT_BG)

    if state.conceal:
        fg = bg
    if state.reverse:
        fg, bg = bg, fg
    if state.dim:
        fg = (int(fg[0] * 0.6), int(fg[1] * 0.6), int(fg[2] * 0.6))

    cw, ch_h = fonts.cell_w, fonts.cell_h

    draw.rectangle([x, y, x + cw - 1, y + ch_h - 1], fill=bg)

    if ch != " ":
        font = _pick_font(fonts, state.bold, state.italic)
        draw.text((x, y), ch, fill=fg, font=font)

    if state.underline:
        draw.line([(x, y + ch_h - 2), (x + cw - 1, y + ch_h - 2)], fill=fg)
    if state.strikethrough:
        mid = y + fonts.ascent // 2
        draw.line([(x, mid), (x + cw - 1, mid)], fill=fg)


def render_lines(
    all_lines: list[str],
    selected: list[int],
    fonts: LoadedFonts,
) -> Image.Image:
    """Render *selected* screen lines to a PIL Image.

    *all_lines* is the full screen capture (needed to replay SGR state from
    the top); *selected* is the list of line indices to render (e.g. from
    grep / head / tail).  Trailing whitespace is trimmed to reduce image width.
    """
    if not selected:
        return Image.new("RGB", (fonts.cell_w, fonts.cell_h), DEFAULT_BG)

    # Build SGR state at the start of every line by simulating from line 0.
    line_states: list[SgrState] = []
    state = SgrState()
    for line in all_lines:
        line_states.append(copy.copy(state))
        state.apply(line)

    # Image width = widest visible content column across selected lines.
    content_cols = max(
        (len(strip_sgr(all_lines[i]).rstrip()) for i in selected),
        default=1,
    )
    content_cols = max(content_cols, 1)

    img_w = content_cols * fonts.cell_w
    img_h = len(selected) * fonts.cell_h

    img = Image.new("RGB", (img_w, img_h), DEFAULT_BG)
    draw = ImageDraw.Draw(img)

    for row, line_idx in enumerate(selected):
        y = row * fonts.cell_h
        x = 0
        cur_state = copy.copy(line_states[line_idx])
        line = all_lines[line_idx]
        pos = 0

        for m in SGR_RE.finditer(line):
            for ch in line[pos : m.start()]:
                if x >= img_w:
                    break
                _render_char(draw, ch, x, y, cur_state, fonts)
                x += fonts.cell_w
            apply_sgr(cur_state, m.group(1))
            pos = m.end()

        for ch in line[pos:]:
            if x >= img_w:
                break
            _render_char(draw, ch, x, y, cur_state, fonts)
            x += fonts.cell_w

    return img


# ─── image saving ────────────────────────────────────────────────────────────


def save_screenshot(img: Image.Image, command: str, session_id: str, ansi_text: str) -> Path:
    """Save *img* to .mockterm-images/ and return the absolute path.

    Also writes a companion .ans file (same base name, .ans extension) containing
    the raw ANSI-escaped text so a human can ``cat`` it in a real terminal for
    comparison.  The .ans path is not printed to stdout.
    """
    out_dir = Path(".mockterm-images")
    out_dir.mkdir(exist_ok=True)
    token = secrets.token_urlsafe(6).lower()
    filename = f"{command}-{session_id}-{token}.png"
    path = out_dir / filename
    img.save(path, format="PNG")
    path.with_suffix(".ans").write_text(ansi_text, encoding="utf-8")
    return path.resolve()


def render_and_save(all_lines: list[str], selected: list[int], command: str, session_id: str) -> str:
    """Render *selected* screen lines to a PNG and return the absolute path.

    Writes the PNG to .mockterm-images/ alongside a .ans companion file
    containing the sanitised ANSI text.  Raises SystemExit with a helpful
    message if no font is available.
    """
    family = find_font_family()
    if family is None:
        raise SystemExit(
            "mockterm: no monospace font found.\n"
            "Install fonts-dejavu-core or fonts-liberation (Ubuntu/Debian)\n"
            "or dejavu-sans-mono-fonts / liberation-mono-fonts (Fedora/RHEL)."
        )
    fonts = load_fonts(family, effective_font_size())
    img = render_lines(all_lines, selected, fonts)
    ansi_text = "\n".join(sanitize_sgr_slice(all_lines, selected))
    path = save_screenshot(img, command, session_id, ansi_text)
    return str(path)
