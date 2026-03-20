# Contributing to octiv-mcp

Thanks for your interest in contributing! This guide covers everything you need to get started.

---

## Reporting bugs

Please [open an issue](../../issues/new) and include:

- A clear description of the problem
- Steps to reproduce it
- What you expected vs. what happened
- Your Python version (`python --version`) and OS

**Security issues:** please do not open a public issue. Email the maintainer directly instead.

---

## Requesting features

[Open an issue](../../issues/new) describing:

- What you want to do that you can't do today
- Why it would be useful to other Octiv users
- Any API endpoints you've discovered that would support it

---

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Clone the repo
git clone https://github.com/<your-org>/octiv-mcp.git
cd octiv-mcp

# Install all dependencies (including dev tools)
uv sync --group dev
```

### Required environment variables

```bash
export OCTIV_USERNAME="your@email.com"
export OCTIV_PASSWORD="yourpassword"
```

Optional (auto-detected from your profile if omitted):

```bash
export OCTIV_TENANT_ID="..."       # Your gym's tenant ID
export OCTIV_LOCATION_ID="..."     # Your gym's location ID
export OCTIV_PROGRAMME_IDS="..."   # Comma-separated WOD programme IDs
```

---

## Running tests

Tests use [respx](https://lundberg.github.io/respx/) to mock all HTTP calls — no real API credentials needed:

```bash
uv run pytest tests/ -v
```

---

## Linting and formatting

This project uses [ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

```bash
# Check for lint issues
uv run ruff check .

# Auto-fix what can be fixed
uv run ruff check . --fix

# Format code
uv run ruff format .
```

---

## Type checking

This project uses [ty](https://github.com/astral-sh/ty) for static type analysis:

```bash
uv run ty check .
```

---

## Before opening a PR

Please make sure all of the following pass:

```bash
uv run ruff check .          # no lint errors
uv run ruff format --check . # code is formatted
uv run ty check .            # no type errors
uv run pytest tests/ -v      # all tests pass
```

---

## PR guidelines

- Keep PRs focused — one feature or fix per PR
- Add or update tests to cover your changes
- Update `README.md` if you change user-facing behaviour or add new tools
- Write clear commit messages

---

## Code style

- Line length: 100 characters
- Strings: double quotes
- Imports: sorted (ruff handles this automatically)
- Type annotations are encouraged on all public functions
