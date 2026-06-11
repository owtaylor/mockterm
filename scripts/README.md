# scripts/

Test scripts for validating mockterm's `--image` rendering quality.  Each
script drives a mockterm session, renders a PNG via `mockterm cat --image`,
and emits JSON describing the content and a set of questions with expected
answers.  The JSON output is meant to be fed to a vision subagent to verify
that the rendered font and layout are legible at the configured size.

Every PNG written by `mockterm --image` automatically gets a companion `.ans`
file (same name, `.ans` extension) containing the raw ANSI-escaped text.
`cat` the `.ans` file in a real terminal to compare against the rendered PNG.

---

## eye-chart.py

Tests basic character legibility and colour/style rendering.

Generates two sections:

- **PLAIN TEXT** — rows of random 4-letter uppercase groups, testing whether
  individual letters can be read accurately.
- **STYLED TEXT** — words rendered with random ANSI foreground colours and
  bold/italic formatting, testing colour and style identification.

The script emits JSON with `png_path`, `questions` (with `expected` answers),
and the `seed` used so any run can be reproduced with `--seed N`.

```sh
python3 scripts/eye-chart.py [--seed N] [--session ID]
```

---

## box-test.py

Tests structural / spatial reasoning: can the model spot a broken box?

Generates rows of words, each enclosed in a Unicode box-drawing box
(`┌─┐ │ └─┘`).  One box per row has a deliberate defect:

| Defect | Description |
|--------|-------------|
| missing corner | `┌`, `┐`, `└`, or `┘` replaced by a space |
| missing side bar | left or right `│` replaced by a space |
| gap in border | 3-char gap punched in the `─` run on the top or bottom |
| width error | top/bottom borders 1 char narrower than the content line, so `┐`/`┘` are misaligned with the right `│` |

The script emits JSON with `png_path`, `rows` (with `broken_word` and
`break_type`), and `questions`.

```sh
python3 scripts/box-test.py [--seed N] [--session ID] [--font-size PX]
```

`--font-size` sets `MOCKTERM_FONT_SIZE` for that run, overriding the compiled-in
default.  Useful for comparing legibility across sizes without editing source.
