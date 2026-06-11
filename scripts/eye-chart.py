#!/usr/bin/env python3
"""
Eye-chart test for mockterm --image rendering quality.

Generates two sections of terminal content:
  • PLAIN TEXT  – rows of random 4-letter groups
  • STYLED TEXT – words with random ANSI colours and bold/italic formatting

Renders both to a PNG via `mockterm cat --image`, then prints JSON with:
  • png_path    – absolute path to the rendered screenshot
  • questions   – list of {type, question, expected, word?} dicts
  • seed        – the random seed used (pass with --seed to reproduce)

Usage:
    python3 scripts/eye-chart.py [--seed N] [--session ID]

The output is meant to be fed to a vision subagent to verify that the
rendered font is legible enough to read individual letters, colours,
and text styles.
"""

import argparse
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import time

# ── layout constants ──────────────────────────────────────────────────────────

GROUPS_PER_LINE = 8   # 4-letter groups per plain-text line
GROUP_SIZE = 4        # letters per group
PLAIN_LINES = 5       # rows in the plain-text section
STYLED_LINES = 4      # rows in the styled section
WORDS_PER_STYLED_LINE = 6

# ── ANSI helpers ──────────────────────────────────────────────────────────────

ESC = "\033"
RESET = f"{ESC}[0m"
BOLD = f"{ESC}[1m"
ITALIC = f"{ESC}[3m"

COLORS: dict[str, str] = {
    "red":     f"{ESC}[31m",
    "green":   f"{ESC}[32m",
    "yellow":  f"{ESC}[33m",
    "blue":    f"{ESC}[34m",
    "magenta": f"{ESC}[35m",
    "cyan":    f"{ESC}[36m",
}

STYLES: dict[str, str] = {
    "normal":      "",
    "bold":        BOLD,
    "italic":      ITALIC,
    "bold italic": BOLD + ITALIC,
}


# ── helpers ───────────────────────────────────────────────────────────────────


def rnd_group(rng: random.Random) -> str:
    return "".join(rng.choices(string.ascii_uppercase, k=GROUP_SIZE))


def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]}"


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None, help="Random seed (printed in output so tests are reproducible)")
    parser.add_argument("--session", default="eye-chart", help="mockterm session name to use")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    rng = random.Random(seed)

    # ── generate data ─────────────────────────────────────────────────────────

    plain_lines: list[list[str]] = [
        [rnd_group(rng) for _ in range(GROUPS_PER_LINE)] for _ in range(PLAIN_LINES)
    ]

    color_names = list(COLORS)
    style_names = list(STYLES)
    styled_lines: list[list[dict[str, str]]] = [
        [
            {
                "word": rnd_group(rng),
                "color": rng.choice(color_names),
                "style": rng.choice(style_names),
            }
            for _ in range(WORDS_PER_STYLED_LINE)
        ]
        for _ in range(STYLED_LINES)
    ]

    # ── build terminal content ────────────────────────────────────────────────

    lines: list[str] = []
    lines.append("=== PLAIN TEXT ===")
    for groups in plain_lines:
        lines.append("  " + "  ".join(groups))

    lines.append("")
    lines.append("=== STYLED TEXT ===")
    for items in styled_lines:
        parts = []
        for item in items:
            esc = COLORS[item["color"]] + STYLES[item["style"]]
            parts.append(f"{esc}{item['word']}{RESET}")
        lines.append("  " + "  ".join(parts))

    content = "\n".join(lines) + "\n"

    # ── render via mockterm ───────────────────────────────────────────────────

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()

        session = args.session
        subprocess.run(["mockterm", "kill", "-s", session], capture_output=True)
        subprocess.run(
            ["mockterm", "start", "-s", session, "--", "sh", "-c", f"cat {tmp.name}; sleep 3600"],
            check=True,
            capture_output=True,
        )
        time.sleep(0.4)

        result = subprocess.run(
            ["mockterm", "cat", "--image", "-s", session],
            capture_output=True,
            text=True,
            check=True,
        )
        png_path = result.stdout.strip()

        subprocess.run(["mockterm", "kill", "-s", session], capture_output=True)
    finally:
        os.unlink(tmp.name)

    # ── generate questions ────────────────────────────────────────────────────

    questions: list[dict[str, str]] = []

    # Five plain-text readability questions
    seen: set[tuple[int, int]] = set()
    while len(questions) < 5:
        li, gi = rng.randint(0, PLAIN_LINES - 1), rng.randint(0, GROUPS_PER_LINE - 1)
        if (li, gi) in seen:
            continue
        seen.add((li, gi))
        questions.append(
            {
                "type": "plain",
                "question": (
                    f"In the PLAIN TEXT section, what four letters make up the "
                    f"{ordinal(gi + 1)} group on line {li + 1}?"
                ),
                "expected": plain_lines[li][gi],
            }
        )

    # Five colour questions
    seen = set()
    while len(questions) < 10:
        li, wi = rng.randint(0, STYLED_LINES - 1), rng.randint(0, WORDS_PER_STYLED_LINE - 1)
        if (li, wi) in seen:
            continue
        seen.add((li, wi))
        item = styled_lines[li][wi]
        questions.append(
            {
                "type": "color",
                "question": (
                    f"In the STYLED TEXT section, what colour is the {ordinal(wi + 1)} word "
                    f"on line {li + 1}? (one of: red, green, yellow, blue, magenta, cyan)"
                ),
                "expected": item["color"],
                "word": item["word"],
            }
        )

    # Five style questions
    seen = set()
    while len(questions) < 15:
        li, wi = rng.randint(0, STYLED_LINES - 1), rng.randint(0, WORDS_PER_STYLED_LINE - 1)
        if (li, wi) in seen:
            continue
        seen.add((li, wi))
        item = styled_lines[li][wi]
        questions.append(
            {
                "type": "style",
                "question": (
                    f"In the STYLED TEXT section, what is the text style of the {ordinal(wi + 1)} word "
                    f"on line {li + 1}? (answer: normal, bold, italic, or bold italic)"
                ),
                "expected": item["style"],
                "word": item["word"],
            }
        )

    # ── emit JSON ─────────────────────────────────────────────────────────────

    print(
        json.dumps(
            {
                "seed": seed,
                "png_path": png_path,
                "plain_lines": plain_lines,
                "styled_lines": styled_lines,
                "questions": questions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
