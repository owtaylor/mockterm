# scripts/

Test scripts for validating mockterm's `--image` rendering quality.
Run `python3 scripts/<name>.py --help` for full usage.

- **eye-chart.py** — generates random 4-letter groups and ANSI-coloured/styled words,
  renders to PNG, and emits JSON with questions and expected answers for
  vision legibility testing.
- **box-test.py** — generates rows of words in Unicode box-drawing boxes with one
  deliberate defect per row; tests whether a vision model can spot structural
  rendering errors.  Accepts `--font-size PX` to drive the `MOCKTERM_FONT_SIZE`
  override for cross-size comparison.
