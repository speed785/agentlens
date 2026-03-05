# Contributing to AgentLens

Thanks for your interest in contributing.

## Development Setup

1. Fork and clone the repository.
2. Set up Python:
   - `cd python`
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -e ".[dev]"`
3. Set up TypeScript:
   - `cd ../typescript`
   - `npm ci`

## Running Tests

- Python:
  - `cd python`
  - `pytest --cov`
- TypeScript:
  - `cd typescript`
  - `npm test`

All contributions must keep test coverage at 100%.

## Pull Request Guidelines

- Keep each PR focused on one feature, fix, or refactor.
- Add or update tests for every behavior change.
- Ensure coverage remains at 100%.
- Update docs and `CHANGELOG.md` for user-facing changes.
- Keep commits clear and scoped.

## Code Style

- Python:
  - Format and lint with `ruff`.
  - Run `ruff check agentlens tests`.
- TypeScript:
  - Lint with `eslint`.
  - Run `npm run lint`.

Before opening a PR, run local checks and ensure CI passes.
