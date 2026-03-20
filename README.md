# Octiv Fitness MCP Server

An MCP (Model Context Protocol) server that connects to the [Octiv Fitness](https://octivfitness.com) API, letting you ask Claude about your gym class schedule and bookings directly in conversation.

## Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- Your Octiv login credentials (email + password)

## Installation

```bash
cd octiv-mcp
uv sync
```

This creates a `.venv` and installs all runtime dependencies. To also install dev tools (ruff, ty, pytest):

```bash
uv sync --group dev
```

## Configuration

The server reads credentials from environment variables:

| Variable | Required | Description |
|---|---|---|
| `OCTIV_USERNAME` | ✅ | Your Octiv login email |
| `OCTIV_PASSWORD` | ✅ | Your Octiv password |
| `OCTIV_TENANT_ID` | Optional | Your gym's tenant ID (auto-detected if omitted) |
| `OCTIV_LOCATION_ID` | Optional | Your gym's location ID (auto-detected if omitted) |
| `OCTIV_PROGRAMME_IDS` | Optional | Comma-separated WOD programme IDs. If omitted, `get_wod` will prompt you to choose from the available programmes. |

The server caches your auth token (~1 year validity) and user profile in `~/.octiv_mcp/` so it doesn't re-login on every call.

## Setting up in Claude Code

Add the server to your Claude Code MCP config. Edit `~/.claude/claude_mcp_config.json` (or create it):

```json
{
  "mcpServers": {
    "octiv": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/octiv-mcp", "python", "/path/to/octiv-mcp/server.py"],
      "env": {
        "OCTIV_USERNAME": "your@email.com",
        "OCTIV_PASSWORD": "yourpassword"
      }
    }
  }
}
```

Then restart Claude Code. You can test it with:
```
/mcp
```

## Setting up in Claude Desktop (Cowork)

Edit your Claude Desktop config at:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "octiv": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/octiv-mcp", "python", "/path/to/octiv-mcp/server.py"],
      "env": {
        "OCTIV_USERNAME": "your@email.com",
        "OCTIV_PASSWORD": "yourpassword"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

## Available Tools

### `get_weekly_schedule`
Fetches the full class schedule for a given week.

**Parameters:**
- `week_offset` (optional, integer): `0` = this week, `1` = next week, `-1` = last week. Defaults to `0`.

**Example prompts:**
- *"What classes are on this week?"*
- *"Show me next week's schedule"*

---

### `get_schedule_for_date`
Fetches the class schedule for a specific date or date range.

**Parameters:**
- `start_date` (required): Date in `YYYY-MM-DD` format
- `end_date` (optional): End date in `YYYY-MM-DD` format (defaults to `start_date`)

**Example prompts:**
- *"What's on tomorrow?"*
- *"Show me classes from Monday to Wednesday"*

---

### `get_my_bookings`
Fetches only the classes **you are personally booked into**.

**Parameters:**
- `start_date` (optional): Defaults to today
- `end_date` (optional): Defaults to 7 days from today

**Example prompts:**
- *"What classes am I booked into this week?"*
- *"What's my schedule for the next 7 days?"*

---

### `get_programmes`
Lists all available training programmes for your gym. Use this to discover programme IDs for filtering WODs.

**Parameters:** none

**Example prompts:**
- *"What programmes does my gym offer?"*
- *"Show me the available programmes"*

---

### `get_wod`
Fetches the **Workout of the Day (WOD)** for a specific date or date range. Returns the warm-up, all exercises (with descriptions and measuring units), and cool-down.

**Parameters:**
- `date` (optional): Date in `YYYY-MM-DD` format. Defaults to today.
- `end_date` (optional): Inclusive end date for a multi-day range. Defaults to `date`.
- `programme_ids` (optional): Comma-separated programme IDs (e.g. `"195,196"`). Falls back to `OCTIV_PROGRAMME_IDS` env var. If neither is set, the tool returns a list of available programmes and asks you to choose one.

**Example prompts:**
- *"What's today's WOD?"*
- *"Show me this week's workouts"*
- *"What's the WOD for Thursday?"*

## Finding your gym's programme IDs

When you first call `get_wod`, if no programme is configured the server will automatically return the list of available programmes at your gym — just pick one and re-ask.

You can also call `get_programmes` at any time to browse the list:

> *"What programmes does my gym offer?"*

Once you know the ID you want, you can either:
- Pass `programme_ids` directly in your prompt: *"What's the CrossFit WOD today? (programme 195)"*
- Or set `OCTIV_PROGRAMME_IDS=195` in your MCP config so it's used automatically

## Notes

- The server connects to `https://api.octivfitness.com`
- Auth tokens are cached in `~/.octiv_mcp/token.json` and are valid for ~1 year
- If you change your password, delete `~/.octiv_mcp/token.json` to force a fresh login
- `OCTIV_TENANT_ID` and `OCTIV_LOCATION_ID` are auto-detected from your profile on first use
- Use `get_programmes` to discover programme IDs available at your gym

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style guidelines, and how to submit a pull request.

## License

MIT — see [LICENSE](LICENSE).

## Testing

Install test dependencies (already included in `requirements.txt`):

```bash
uv sync --group dev
```

Run the full test suite:

```bash
uv run pytest tests/ -v
```

Lint and format:

```bash
uv run ruff check .
uv run ruff format .
```

Type check:

```bash
uv run ty check .
```

Tests use [respx](https://lundberg.github.io/respx/) to mock all HTTP calls — no real API credentials needed.
