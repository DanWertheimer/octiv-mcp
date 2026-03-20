"""Tests for MCP tool call handlers (all tools, mocked OctivClient)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.types import TextContent

from server import call_tool

ME_RESPONSE = {
    "id": 42,
    "userTenant": {"tenantId": 101134, "defaultLocationId": 1091},
}
EMPTY_CLASS_DATA = {"data": [], "meta": {}}
EMPTY_WOD_DATA = {"data": [], "meta": {}}
PROGRAMMES_DATA = {
    "data": [
        {"id": 195, "name": "CrossFit", "description": "Daily CrossFit WOD"},
        {"id": 196, "name": "Weightlifting", "description": "Olympic lifting"},
    ],
    "meta": {},
}
WOD_DATA = {
    "data": [
        {
            "id": 599450,
            "date": "2026-03-19",
            "warmUp": "10 min warm-up",
            "coolDown": "5 min cool-down",
            "coachNotes": None,
            "memberNotes": None,
            "wodExercises": [
                {
                    "id": 1,
                    "isActive": 1,
                    "order": 1,
                    "wodId": 599450,
                    "exerciseId": 100,
                    "exercise": {
                        "id": 100,
                        "name": "Clean strength",
                        "description": "6 Min EMOM",
                        "measuringUnit": {"id": 1, "name": "For Weight - kg", "unit": "kg"},
                    },
                }
            ],
        }
    ],
    "meta": {},
}


@pytest.fixture
def mock_client():
    with patch("server._client") as mock:
        mock.get_me = AsyncMock(return_value=ME_RESPONSE)
        mock.get_class_dates = AsyncMock(return_value=EMPTY_CLASS_DATA)
        mock.get_programmes = AsyncMock(return_value=PROGRAMMES_DATA)
        mock.get_wods = AsyncMock(return_value=WOD_DATA)
        mock._extract_gym_ids = MagicMock(return_value=("101134", "1091"))
        yield mock


# ── get_weekly_schedule ───────────────────────────────────────────────────────


async def test_get_weekly_schedule_structure(mock_client):
    result = await call_tool("get_weekly_schedule", {})
    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    data = json.loads(result[0].text)
    assert "week" in data
    assert "totalClasses" in data
    assert "classes" in data


async def test_get_weekly_schedule_with_offset(mock_client):
    result = await call_tool("get_weekly_schedule", {"week_offset": 1})
    data = json.loads(result[0].text)
    assert "week" in data
    mock_client.get_class_dates.assert_called_once()


async def test_get_weekly_schedule_default_offset_is_zero(mock_client):
    await call_tool("get_weekly_schedule", {})
    await call_tool("get_weekly_schedule", {"week_offset": 0})
    # Both should call with the same date range
    first_call = mock_client.get_class_dates.call_args_list[0]
    second_call = mock_client.get_class_dates.call_args_list[1]
    assert first_call == second_call


# ── get_schedule_for_date ─────────────────────────────────────────────────────


async def test_get_schedule_for_date_single_day(mock_client):
    result = await call_tool("get_schedule_for_date", {"start_date": "2026-03-20"})
    data = json.loads(result[0].text)
    assert data["dateRange"] == "2026-03-20"
    assert "classes" in data


async def test_get_schedule_for_date_range(mock_client):
    result = await call_tool(
        "get_schedule_for_date",
        {
            "start_date": "2026-03-20",
            "end_date": "2026-03-22",
        },
    )
    data = json.loads(result[0].text)
    assert data["dateRange"] == "2026-03-20 to 2026-03-22"


async def test_get_schedule_for_date_calls_client_correctly(mock_client):
    await call_tool("get_schedule_for_date", {"start_date": "2026-03-20", "end_date": "2026-03-22"})
    mock_client.get_class_dates.assert_called_once_with("2026-03-20", "2026-03-22")


# ── get_my_bookings ───────────────────────────────────────────────────────────


async def test_get_my_bookings_structure(mock_client):
    result = await call_tool("get_my_bookings", {})
    data = json.loads(result[0].text)
    assert "bookings" in data
    assert "myBookingsCount" in data
    assert "dateRange" in data


async def test_get_my_bookings_filters_to_my_classes(mock_client):
    class_with_booking = {
        "id": 1,
        "date": "2026-03-20",
        "name": "CrossFit",
        "startTime": "06:00:00",
        "endTime": "07:00:00",
        "instructor": {"name": "Jane", "surname": "Doe"},
        "limit": 20,
        "bookings": [{"userId": 42, "status": {"name": "BOOKED"}}],
        "waitingListCount": 0,
        "description": "",
    }
    mock_client.get_class_dates.return_value = {"data": [class_with_booking]}
    result = await call_tool("get_my_bookings", {})
    data = json.loads(result[0].text)
    assert data["myBookingsCount"] == 1


# ── get_programmes ────────────────────────────────────────────────────────────


async def test_get_programmes_structure(mock_client):
    result = await call_tool("get_programmes", {})
    data = json.loads(result[0].text)
    assert "programmes" in data
    assert "total" in data
    assert data["total"] == 2


async def test_get_programmes_includes_id_and_name(mock_client):
    result = await call_tool("get_programmes", {})
    data = json.loads(result[0].text)
    first = data["programmes"][0]
    assert first["id"] == 195
    assert first["name"] == "CrossFit"


# ── get_wod ───────────────────────────────────────────────────────────────────


async def test_get_wod_structure(mock_client):
    result = await call_tool("get_wod", {"programme_ids": "195"})
    data = json.loads(result[0].text)
    assert "wods" in data
    assert "totalWods" in data
    assert "dateRange" in data


async def test_get_wod_defaults_to_single_day(mock_client):
    await call_tool("get_wod", {"date": "2026-03-19", "programme_ids": "195"})
    # end_exclusive should be start + 1 day
    mock_client.get_wods.assert_called_once_with("2026-03-19", "2026-03-20", "195")


async def test_get_wod_multi_day_range(mock_client):
    await call_tool(
        "get_wod", {"date": "2026-03-19", "end_date": "2026-03-21", "programme_ids": "195"}
    )
    mock_client.get_wods.assert_called_once_with("2026-03-19", "2026-03-22", "195")


async def test_get_wod_passes_programme_ids(mock_client):
    await call_tool("get_wod", {"date": "2026-03-19", "programme_ids": "195,196"})
    mock_client.get_wods.assert_called_once_with("2026-03-19", "2026-03-20", "195,196")


async def test_get_wod_formats_exercises(mock_client):
    result = await call_tool("get_wod", {"date": "2026-03-19", "programme_ids": "195"})
    data = json.loads(result[0].text)
    wod = data["wods"][0]
    assert wod["warmUp"] == "10 min warm-up"
    assert len(wod["exercises"]) == 1
    assert wod["exercises"][0]["name"] == "Clean strength"


async def test_get_wod_single_day_daterange_is_just_date(mock_client):
    result = await call_tool("get_wod", {"date": "2026-03-19", "programme_ids": "195"})
    data = json.loads(result[0].text)
    assert data["dateRange"] == "2026-03-19"


async def test_get_wod_multi_day_daterange_includes_both(mock_client):
    result = await call_tool(
        "get_wod", {"date": "2026-03-19", "end_date": "2026-03-21", "programme_ids": "195"}
    )
    data = json.loads(result[0].text)
    assert data["dateRange"] == "2026-03-19 to 2026-03-21"


async def test_get_wod_without_programme_returns_select_programme(mock_client, monkeypatch):
    monkeypatch.delenv("OCTIV_PROGRAMME_IDS", raising=False)
    result = await call_tool("get_wod", {"date": "2026-03-19"})
    data = json.loads(result[0].text)
    assert data["action"] == "select_programme"
    assert "availableProgrammes" in data
    assert len(data["availableProgrammes"]) == 2
    mock_client.get_wods.assert_not_called()


async def test_get_wod_env_var_bypasses_discovery(mock_client, monkeypatch):
    monkeypatch.setenv("OCTIV_PROGRAMME_IDS", "195")
    await call_tool("get_wod", {"date": "2026-03-19"})
    mock_client.get_wods.assert_called_once_with("2026-03-19", "2026-03-20", "195")


# ── error handling ────────────────────────────────────────────────────────────


async def test_unknown_tool_returns_error_text(mock_client):
    result = await call_tool("nonexistent_tool", {})
    assert isinstance(result[0], TextContent)
    assert "Unknown tool" in result[0].text


async def test_http_status_error_returns_error_message(mock_client):
    mock_client.get_class_dates.side_effect = httpx.HTTPStatusError(
        "error",
        request=MagicMock(),
        response=MagicMock(status_code=500, text="Internal Server Error"),
    )
    result = await call_tool("get_schedule_for_date", {"start_date": "2026-03-20"})
    assert "API error 500" in result[0].text


async def test_generic_exception_returns_error_message(mock_client):
    mock_client.get_programmes.side_effect = RuntimeError("Unexpected failure")
    result = await call_tool("get_programmes", {})
    assert "RuntimeError" in result[0].text
    assert "Unexpected failure" in result[0].text
