**NOTE**: CLAUDE.md is a symlink to AGENTS.md, this file. AGENTS.md doesn't need to be
read or updated separately.

## How to work

As an agent, you expected to work autonomously as part of a team with a human
programmer. Given a task, try to create a complete change that is ready to be
filed as a pull request, but stop and let the human review it before actually
filing the pull request.

## Tech stack

 * uv
 * pyright
 * ruff
 * GitHub actions for CI
 * tmux as the terminal handling backend

## Running checks locally

Before committing, run the same checks that CI runs:

```sh
uv run ruff check src/ tests/   # lint
uv run ruff format --check src/ tests/  # formatting
uv run pyright                  # type check
uv run pytest -v                # tests (requires tmux)
```
