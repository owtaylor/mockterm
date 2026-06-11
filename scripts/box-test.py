#!/usr/bin/env python3
"""
Box-drawing eye test for mockterm --image.

Generates rows of four words, each enclosed in a box drawn with Unicode
box-drawing characters.  One box per row has a deliberate defect (a missing
corner, a missing side bar, or a gap in a border), simulating the kind of
rendering bug an agent might need to spot in a TUI program.

The subagent must report which word has the broken box on each row.

Usage:
    python3 scripts/box-test.py [--seed N] [--session ID]
"""

import argparse
import json
import os
import random
import subprocess
import tempfile
import time

# ── content ───────────────────────────────────────────────────────────────────

WORDS = [
    "Aardvark", "Banana", "Cherry", "Dragon", "Elephant",
    "Falcon", "Gorilla", "Hamster", "Iguana", "Jaguar",
    "Koala", "Lemur", "Mango", "Narwhal", "Octopus",
    "Penguin", "Quokka", "Rabbit", "Salmon", "Tiger",
]

BOXES_PER_ROW = 4
NUM_ROWS = 5
PADDING = 2  # spaces on each side of the word inside the box
BOX_SEP = "   "  # gap between boxes on a row

# ── break types ───────────────────────────────────────────────────────────────

# Each entry: (key, human description)
BREAK_TYPES: list[tuple[str, str]] = [
    ("missing_top_left",    "missing top-left corner ┌"),
    ("missing_top_right",   "missing top-right corner ┐"),
    ("gap_top",             "gap in the top border ─"),
    ("missing_left_side",   "missing left side bar │"),
    ("missing_right_side",  "missing right side bar │"),
    ("missing_bottom_left", "missing bottom-left corner └"),
    ("missing_bottom_right","missing bottom-right corner ┘"),
    ("gap_bottom",          "gap in the bottom border ─"),
    ("width_error",         "width error: right │ not aligned with ┐/┘ corners"),
]
BREAK_KEYS = [k for k, _ in BREAK_TYPES]
BREAK_DESC = dict(BREAK_TYPES)

# ── box rendering ─────────────────────────────────────────────────────────────


def make_box(word: str, inner_w: int, break_key: str | None) -> tuple[str, str, str]:
    """Return (top_line, content_line, bottom_line) for one box.

    inner_w is the number of characters between the left and right borders,
    including the padding spaces either side of the word.

    All three returned strings are guaranteed to be the same length (inner_w + 2)
    regardless of break_key, so boxes can be joined with a fixed separator without
    misaligning subsequent boxes on the same row.
    """
    content = word.center(inner_w)

    tl, tr = "┌", "┐"
    bl, br = "└", "┘"
    vl, vr = "│", "│"
    top_h = "─" * inner_w
    bot_h = "─" * inner_w

    if break_key == "width_error":
        # Top and bottom borders are 1 char narrower than the content line,
        # so ┐/┘ appear 1 column to the left of the right │.
        # A trailing space keeps total line width identical to a normal box
        # so subsequent boxes on the same row are not affected.
        short_h = "─" * (inner_w - 1)
        return (
            tl + short_h + tr + " ",
            vl + content + vr,
            bl + short_h + br + " ",
        )

    if break_key == "missing_top_left":
        tl = " "
    elif break_key == "missing_top_right":
        tr = " "
    elif break_key == "gap_top":
        mid = inner_w // 2
        top_h = "─" * (mid - 1) + "   " + "─" * (inner_w - mid - 2)
    elif break_key == "missing_left_side":
        vl = " "
    elif break_key == "missing_right_side":
        vr = " "
    elif break_key == "missing_bottom_left":
        bl = " "
    elif break_key == "missing_bottom_right":
        br = " "
    elif break_key == "gap_bottom":
        mid = inner_w // 2
        bot_h = "─" * (mid - 1) + "   " + "─" * (inner_w - mid - 2)

    return (
        tl + top_h + tr,
        vl + content + vr,
        bl + bot_h + br,
    )


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--session", default="box-test")
    parser.add_argument("--font-size", type=int, default=None, metavar="PX",
                        help="Override render font size (sets MOCKTERM_FONT_SIZE env var).")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    rng = random.Random(seed)

    # Pick words without repetition
    words_flat = rng.sample(WORDS, BOXES_PER_ROW * NUM_ROWS)

    # inner_w: longest word + padding on each side
    max_word_len = max(len(w) for w in words_flat)
    inner_w = max_word_len + PADDING * 2

    # Assign one broken box per row
    rows: list[dict] = []
    for r in range(NUM_ROWS):
        row_words = words_flat[r * BOXES_PER_ROW : (r + 1) * BOXES_PER_ROW]
        broken_pos = rng.randint(0, BOXES_PER_ROW - 1)
        break_key = rng.choice(BREAK_KEYS)
        rows.append({"words": row_words, "broken_pos": broken_pos, "break_key": break_key})

    # Build terminal content
    output_lines: list[str] = []
    for row_num, row in enumerate(rows, 1):
        tops, mids, bots = [], [], []
        for i, word in enumerate(row["words"]):
            bk = row["break_key"] if i == row["broken_pos"] else None
            top, mid, bot = make_box(word, inner_w, bk)
            tops.append(top)
            mids.append(mid)
            bots.append(bot)
        output_lines.append(f"Row {row_num}:")
        output_lines.append(BOX_SEP.join(tops))
        output_lines.append(BOX_SEP.join(mids))
        output_lines.append(BOX_SEP.join(bots))
        output_lines.append("")

    content = "\n".join(output_lines) + "\n"

    # Render via mockterm
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()

        session = args.session
        subprocess.run(["mockterm", "kill", "-s", session], capture_output=True)
        subprocess.run(
            [
                "mockterm", "start", "-s", session,
                "--", "sh", "-c", f"cat {tmp.name}; sleep 3600",
            ],
            check=True,
            capture_output=True,
        )
        time.sleep(0.4)

        result = subprocess.run(
            ["mockterm", "cat", "--image", "-s", session],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **({"MOCKTERM_FONT_SIZE": str(args.font_size)} if args.font_size else {})},
        )
        png_path = result.stdout.strip()

        subprocess.run(["mockterm", "kill", "-s", session], capture_output=True)
    finally:
        os.unlink(tmp.name)

    # Generate questions
    questions = []
    for i, row in enumerate(rows):
        questions.append(
            {
                "question": (
                    f"Row {i + 1} contains the words: {', '.join(row['words'])}. "
                    f"Exactly one of their boxes has a defect. Which word has the broken box?"
                ),
                "expected": row["words"][row["broken_pos"]],
                "break_type": BREAK_DESC[row["break_key"]],
            }
        )

    print(
        json.dumps(
            {
                "seed": seed,
                "png_path": png_path,
                "rows": [
                    {
                        "words": r["words"],
                        "broken_word": r["words"][r["broken_pos"]],
                        "break_type": BREAK_DESC[r["break_key"]],
                    }
                    for r in rows
                ],
                "questions": questions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
