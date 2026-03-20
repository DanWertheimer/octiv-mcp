#!/usr/bin/env python3
"""
Octiv Fitness MCP Server
Connects to the Octiv Fitness API to fetch gym class schedules and bookings.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Constants ──────────────────────────────────────────────────────────────────
API_BASE = "https://api.octivfitness.com"
TOKEN_CACHE_PATH = Path.home() / ".octiv_mcp" / "token.json"
USER_CACHE_PATH = Path.home() / ".octiv_mcp" / "user.json"

# ── Octiv API Client ───────────────────────────────────────────────────────────


class OctivClient:
    def __init__(self):
        self.username = os.environ.get("OCTIV_USERNAME") or os.environ.get("OCTIV_EMAIL", "")
        self.password = os.environ.get("OCTIV_PASSWORD", "")
        if not self.username or not self.password:
            raise ValueError(
                "OCTIV_USERNAME (or OCTIV_EMAIL) and OCTIV_PASSWORD "
                "environment variables must be set."
            )
        self._token: str | None = None
        self._user_info: dict | None = None

    # ── Token management ──────────────────────────────────────────────────────

    def _load_cached_token(self) -> str | None:
        """Load a cached token if it's still valid (with 1-hour buffer)."""
        if TOKEN_CACHE_PATH.exists():
            try:
                data = json.loads(TOKEN_CACHE_PATH.read_text())
                if data.get("expires_at", 0) > time.time() + 3600:
                    return data["access_token"]
            except Exception:
                pass
        return None

    def _save_token(self, token_data: dict) -> None:
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(
            json.dumps(
                {
                    "access_token": token_data["accessToken"],
                    "expires_at": time.time() + token_data.get("expiresIn", 31536000),
                }
            )
        )

    async def get_token(self) -> str:
        if self._token:
            return self._token
        cached = self._load_cached_token()
        if cached:
            self._token = cached
            return self._token
        # Perform fresh login
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{API_BASE}/api/login",
                json={"username": self.username, "password": self.password},
            )
            resp.raise_for_status()
            data = resp.json()
            self._save_token(data)
            self._token = data["accessToken"]
            return self._token

    def _invalidate_token(self):
        """Clear cached token so the next call triggers a fresh login."""
        self._token = None
        if TOKEN_CACHE_PATH.exists():
            TOKEN_CACHE_PATH.unlink()

    async def _headers(self) -> dict:
        token = await self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ── User / gym info ───────────────────────────────────────────────────────

    def _load_cached_user(self) -> dict | None:
        if USER_CACHE_PATH.exists():
            try:
                return json.loads(USER_CACHE_PATH.read_text())
            except Exception:
                pass
        return None

    def _save_user(self, user: dict) -> None:
        USER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_CACHE_PATH.write_text(json.dumps(user))

    async def get_me(self) -> dict:
        """Return the current user's profile, cached to disk."""
        if self._user_info:
            return self._user_info
        cached = self._load_cached_user()
        if cached:
            self._user_info = cached
            return self._user_info
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{API_BASE}/me", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            self._save_user(data)
            self._user_info = data
            return data

    def _extract_gym_ids(self, me: dict) -> tuple[str, str]:
        """
        Extract tenantId and locationId from environment variables or the /me profile response.
        Raises ValueError with setup instructions if neither source provides the IDs.
        """
        # Env vars take precedence (allows per-user override)
        tenant_id = os.environ.get("OCTIV_TENANT_ID")
        location_id = os.environ.get("OCTIV_LOCATION_ID")

        if not tenant_id or not location_id:
            # Auto-detect from the profile returned by /me
            user_tenant = me.get("userTenant") or {}
            tenant_id = tenant_id or str(user_tenant.get("tenantId", ""))
            location_id = location_id or str(user_tenant.get("defaultLocationId") or "")

        if not tenant_id:
            raise ValueError(
                "Could not determine your gym's tenant ID. "
                "Please set the OCTIV_TENANT_ID environment variable. "
                "You can find this value by inspecting the Octiv web app network requests."
            )
        if not location_id:
            raise ValueError(
                "Could not determine your gym's location ID. "
                "Please set the OCTIV_LOCATION_ID environment variable. "
                "You can find this value by inspecting the Octiv web app network requests."
            )
        return tenant_id, location_id

    # ── Class schedule ────────────────────────────────────────────────────────

    async def get_class_dates(self, start_date: str, end_date: str) -> dict:
        """
        Fetch class dates (and their bookings) between start_date and end_date.
        Both dates should be in YYYY-MM-DD format.
        """
        headers = await self._headers()
        me = await self.get_me()
        tenant_id, location_id = self._extract_gym_ids(me)

        params = {
            "include": "classBookings.user",
            "filter[tenantId]": tenant_id,
            "filter[locationId]": location_id,
            "filter[between]": f"{start_date},{end_date}",
            "filter[isSession]": "0",
            "internalAppend": "withoutLocations",
            "perPage": "-1",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{API_BASE}/class-dates", headers=headers, params=params)
            if resp.status_code == 401:
                self._invalidate_token()
                raise ValueError("Authentication expired. Please retry.")
            resp.raise_for_status()
            return resp.json()

    async def get_programmes(self) -> dict:
        """Fetch all training programmes for this tenant."""
        headers = await self._headers()
        me = await self.get_me()
        tenant_id, _ = self._extract_gym_ids(me)
        params = {
            "filter[tenantId]": tenant_id,
            "perPage": "-1",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{API_BASE}/api/programmes", headers=headers, params=params)
            if resp.status_code == 401:
                self._invalidate_token()
                raise ValueError("Authentication expired. Please retry.")
            resp.raise_for_status()
            return resp.json()

    async def get_wods(
        self, start_date: str, end_date: str, programme_ids: str | None = None
    ) -> dict:
        """
        Fetch WODs where startsAfter=start_date and endsBefore=end_date (exclusive upper bound).
        Both dates should be in YYYY-MM-DD format.
        """
        headers = await self._headers()
        me = await self.get_me()
        tenant_id, _ = self._extract_gym_ids(me)
        pids = programme_ids or os.environ.get("OCTIV_PROGRAMME_IDS")
        params: dict[str, str] = {
            "filter[tenantId]": tenant_id,
            "filter[startsAfter]": start_date,
            "filter[endsBefore]": end_date,
            "filter[useWorkoutThreshold]": "1",
        }
        if pids:
            params["filter[programmeIds]"] = pids
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{API_BASE}/api/wods", headers=headers, params=params)
            if resp.status_code == 401:
                self._invalidate_token()
                raise ValueError("Authentication expired. Please retry.")
            resp.raise_for_status()
            return resp.json()


def _format_time(t: str) -> str:
    """Convert 'HH:MM:SS' to 'H:MM AM/PM'."""
    try:
        return datetime.strptime(t, "%H:%M:%S").strftime("%-I:%M %p")
    except Exception:
        return t


def format_schedule(data: dict, my_user_id: int | None = None) -> list[dict]:
    """Convert raw API class-dates response into a clean list of class summaries."""
    classes = data.get("data", [])
    result = []

    for cls in classes:
        bookings = cls.get("bookings", [])
        active_bookings = [b for b in bookings if b.get("status", {}).get("name") == "BOOKED"]
        wait_list = cls.get("waitingListCount", 0)

        instructor = cls.get("instructor") or {}
        instructor_name = (
            f"{instructor.get('name', '')} {instructor.get('surname', '')}".strip() or "TBA"
        )

        summary = {
            "classDateId": cls["id"],
            "date": cls["date"],
            "name": cls["name"],
            "startTime": _format_time(cls["startTime"]),
            "endTime": _format_time(cls["endTime"]),
            "instructor": instructor_name,
            "capacity": cls["limit"],
            "booked": len(active_bookings),
            "available": max(0, cls["limit"] - len(active_bookings)),
            "waitingList": wait_list,
            "description": cls.get("description") or "",
        }

        # Highlight if the current user is booked
        if my_user_id:
            my_booking = next((b for b in bookings if b.get("userId") == my_user_id), None)
            if my_booking:
                status = my_booking.get("status", {}).get("name", "UNKNOWN")
                summary["myBooking"] = {
                    "status": status,
                    "checkedIn": my_booking.get("checkedInAt") is not None,
                    "checkedOut": my_booking.get("checkedOutAt") is not None,
                }

        result.append(summary)

    return result


def _week_bounds(offset_weeks: int = 0) -> tuple[str, str]:
    """Return Monday and Sunday of the current (or offset) week as YYYY-MM-DD."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def format_wod(data: dict) -> list[dict]:
    """Convert raw /api/wods response into a clean list of WOD summaries."""
    wods = data.get("data", [])
    result = []
    for wod in wods:
        exercises = []
        for we in sorted(wod.get("wodExercises", []), key=lambda x: x.get("order", 0)):
            if not we.get("isActive", 1):
                continue
            ex = we.get("exercise", {})
            mu = ex.get("measuringUnit", {})
            exercises.append(
                {
                    "order": we.get("order"),
                    "name": ex.get("name", ""),
                    "description": (ex.get("description") or "").strip(),
                    "measuringUnit": mu.get("name", ""),
                }
            )
        result.append(
            {
                "id": wod["id"],
                "date": wod.get("date", ""),
                "warmUp": (wod.get("warmUp") or "").strip(),
                "coolDown": (wod.get("coolDown") or "").strip(),
                "coachNotes": (wod.get("coachNotes") or "").strip(),
                "memberNotes": (wod.get("memberNotes") or "").strip(),
                "exercises": exercises,
            }
        )
    return result


# ── MCP Server ─────────────────────────────────────────────────────────────────

server = Server("octiv-mcp")
_client = OctivClient()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_weekly_schedule",
            description=(
                "Fetch the full class schedule for the current week (Monday–Sunday) "
                "from Octiv Fitness. Shows all classes with times, instructor, capacity, "
                "and whether you are booked in."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "week_offset": {
                        "type": "integer",
                        "description": (
                            "0 = current week, 1 = next week, -1 = last week. Defaults to 0."
                        ),
                        "default": 0,
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_schedule_for_date",
            description=(
                "Fetch the class schedule for a specific date or date range from Octiv Fitness."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "End date in YYYY-MM-DD format. "
                            "If omitted, defaults to start_date (single day)."
                        ),
                    },
                },
                "required": ["start_date"],
            },
        ),
        Tool(
            name="get_my_bookings",
            description=(
                "Fetch the classes you are personally booked into for a given date range. "
                "Defaults to the current week if no dates are provided."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format. Defaults to today.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "End date in YYYY-MM-DD format. Defaults to 7 days from start."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_programmes",
            description=(
                "List all available training programmes for your gym. "
                "Use this to discover programme IDs (e.g. to pass to get_wod)."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_wod",
            description=(
                "Fetch the Workout of the Day (WOD) from Octiv Fitness "
                "for a specific date or date range. "
                "Returns the warm-up, exercises (with descriptions and measuring units), "
                "and cool-down. "
                "If no programme is specified and OCTIV_PROGRAMME_IDS is not set, "
                "returns the available programmes so the user can choose one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format. Defaults to today.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "Inclusive end date in YYYY-MM-DD format for a multi-day range. "
                            "Defaults to date (single day)."
                        ),
                    },
                    "programme_ids": {
                        "type": "string",
                        "description": (
                            "Comma-separated programme IDs to filter by. "
                            "If omitted, falls back to OCTIV_PROGRAMME_IDS env var. "
                            "If neither is set, available programmes are returned instead. "
                            "Use get_programmes to discover available IDs."
                        ),
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        me = await _client.get_me()
        my_user_id: int | None = me.get("id")

        if name == "get_weekly_schedule":
            offset = int(arguments.get("week_offset", 0))
            start, end = _week_bounds(offset)
            raw = await _client.get_class_dates(start, end)
            schedule = format_schedule(raw, my_user_id)
            tenant_id, location_id = _client._extract_gym_ids(me)

            output = {
                "week": f"{start} to {end}",
                "gym": {
                    "tenantId": tenant_id,
                    "locationId": location_id,
                },
                "totalClasses": len(schedule),
                "classes": schedule,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "get_schedule_for_date":
            start = arguments["start_date"]
            end = arguments.get("end_date", start)
            raw = await _client.get_class_dates(start, end)
            schedule = format_schedule(raw, my_user_id)

            output = {
                "dateRange": f"{start} to {end}" if start != end else start,
                "totalClasses": len(schedule),
                "classes": schedule,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "get_my_bookings":
            today = datetime.now().date()
            start = arguments.get("start_date", today.isoformat())
            end = arguments.get("end_date", (today + timedelta(days=6)).isoformat())
            raw = await _client.get_class_dates(start, end)
            all_classes = format_schedule(raw, my_user_id)

            # Filter to only classes where the user has a booking
            my_classes = [c for c in all_classes if "myBooking" in c]

            output = {
                "dateRange": f"{start} to {end}",
                "myBookingsCount": len(my_classes),
                "bookings": my_classes,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "get_programmes":
            raw = await _client.get_programmes()
            programmes = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                }
                for p in raw.get("data", [])
            ]
            output = {"total": len(programmes), "programmes": programmes}
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        elif name == "get_wod":
            today = datetime.now().date()
            date_str = arguments.get("date", today.isoformat())
            end_inclusive = arguments.get("end_date", date_str)
            end_exclusive = (
                datetime.strptime(end_inclusive, "%Y-%m-%d").date() + timedelta(days=1)
            ).isoformat()
            programme_ids = arguments.get("programme_ids") or os.environ.get("OCTIV_PROGRAMME_IDS")

            # If no programme is configured, guide the user to select one
            if not programme_ids:
                raw_programmes = await _client.get_programmes()
                programmes = [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "description": p.get("description"),
                    }
                    for p in raw_programmes.get("data", [])
                ]
                output = {
                    "action": "select_programme",
                    "message": (
                        "No programme selected. "
                        "Please choose one of the available programmes and re-ask for the WOD."
                    ),
                    "availableProgrammes": programmes,
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            raw = await _client.get_wods(date_str, end_exclusive, programme_ids)
            wods = format_wod(raw)
            output = {
                "dateRange": (
                    f"{date_str} to {end_inclusive}" if end_inclusive != date_str else date_str
                ),
                "totalWods": len(wods),
                "wods": wods,
            }
            return [TextContent(type="text", text=json.dumps(output, indent=2))]

        else:
            raise ValueError(f"Unknown tool: {name!r}")

    except httpx.HTTPStatusError as e:
        return [
            TextContent(
                type="text",
                text=f"API error {e.response.status_code}: {e.response.text}",
            )
        ]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


# ── Entry point ────────────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
