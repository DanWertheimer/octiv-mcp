"""Tests for pure formatting helper functions."""

from datetime import date
from typing import Any

from server import _format_time, _week_bounds, format_schedule, format_wod

# ── _format_time ──────────────────────────────────────────────────────────────


class TestFormatTime:
    def test_valid_time_returns_nonempty(self):
        result = _format_time("06:00:00")
        assert result  # always returns something

    def test_valid_time_contains_hour(self):
        result = _format_time("06:00:00")
        # On Linux: "6:00 AM"; on Windows the %-I directive is unsupported
        # so the except branch returns the raw string "06:00:00".
        assert "6" in result or "06" in result

    def test_noon(self):
        result = _format_time("12:00:00")
        assert "12" in result

    def test_invalid_time_returns_input(self):
        assert _format_time("not-a-time") == "not-a-time"

    def test_empty_string_returns_empty(self):
        assert _format_time("") == ""


# ── _week_bounds ──────────────────────────────────────────────────────────────


class TestWeekBounds:
    def test_offset_zero_is_monday_to_sunday(self):
        start, end = _week_bounds(0)
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
        assert start_d.weekday() == 0  # Monday
        assert end_d.weekday() == 6  # Sunday
        assert (end_d - start_d).days == 6

    def test_next_week_is_7_days_later(self):
        s0, _ = _week_bounds(0)
        s1, _ = _week_bounds(1)
        assert (date.fromisoformat(s1) - date.fromisoformat(s0)).days == 7

    def test_last_week_is_7_days_earlier(self):
        s0, _ = _week_bounds(0)
        sm1, _ = _week_bounds(-1)
        assert (date.fromisoformat(s0) - date.fromisoformat(sm1)).days == 7

    def test_returns_iso_format_strings(self):
        start, end = _week_bounds(0)
        # Should not raise
        date.fromisoformat(start)
        date.fromisoformat(end)


# ── format_schedule ───────────────────────────────────────────────────────────

SAMPLE_CLASS = {
    "id": 101,
    "date": "2026-03-20",
    "name": "CrossFit",
    "startTime": "06:00:00",
    "endTime": "07:00:00",
    "instructor": {"name": "Jane", "surname": "Doe"},
    "limit": 20,
    "bookings": [
        {"userId": 1, "status": {"name": "BOOKED"}},
        {"userId": 2, "status": {"name": "BOOKED"}},
        {"userId": 3, "status": {"name": "CANCELLED"}},
    ],
    "waitingListCount": 2,
    "description": "A great class",
}

SAMPLE_CLASS_DATA = {"data": [SAMPLE_CLASS]}


class TestFormatSchedule:
    def test_basic_fields(self):
        result = format_schedule(SAMPLE_CLASS_DATA)
        assert len(result) == 1
        cls = result[0]
        assert cls["classDateId"] == 101
        assert cls["date"] == "2026-03-20"
        assert cls["name"] == "CrossFit"
        assert cls["capacity"] == 20
        assert cls["instructor"] == "Jane Doe"

    def test_counts_only_booked_status(self):
        result = format_schedule(SAMPLE_CLASS_DATA)
        cls = result[0]
        assert cls["booked"] == 2  # CANCELLED is excluded
        assert cls["available"] == 18

    def test_waiting_list(self):
        result = format_schedule(SAMPLE_CLASS_DATA)
        assert result[0]["waitingList"] == 2

    def test_my_booking_present_when_matched(self):
        result = format_schedule(SAMPLE_CLASS_DATA, my_user_id=1)
        cls = result[0]
        assert "myBooking" in cls
        assert cls["myBooking"]["status"] == "BOOKED"

    def test_my_booking_absent_when_not_matched(self):
        result = format_schedule(SAMPLE_CLASS_DATA, my_user_id=99)
        assert "myBooking" not in result[0]

    def test_available_clamped_to_zero_when_overbooked(self):
        data = {
            "data": [
                {
                    **SAMPLE_CLASS,
                    "bookings": [{"userId": i, "status": {"name": "BOOKED"}} for i in range(25)],
                }
            ]
        }
        result = format_schedule(data)
        assert result[0]["available"] == 0

    def test_empty_data_returns_empty_list(self):
        assert format_schedule({"data": []}) == []

    def test_missing_instructor_falls_back_to_tba(self):
        data = {"data": [{**SAMPLE_CLASS, "instructor": None}]}
        result = format_schedule(data)
        assert result[0]["instructor"] == "TBA"


# ── format_wod ────────────────────────────────────────────────────────────────

SAMPLE_WOD_DATA: dict[str, Any] = {
    "data": [
        {
            "id": 599450,
            "date": "2026-03-19",
            "warmUp": "  10 min warm-up  ",
            "coolDown": "5 min cool-down",
            "coachNotes": None,
            "memberNotes": None,
            "wodExercises": [
                {
                    "id": 2,
                    "isActive": 1,
                    "order": 2,
                    "wodId": 599450,
                    "exerciseId": 200,
                    "exercise": {
                        "id": 200,
                        "name": "Big bolt",
                        "description": "17 Min amrap",
                        "measuringUnit": {
                            "id": 9,
                            "name": "For Rounds & Reps",
                            "unit": "rnds.reps",
                        },
                    },
                },
                {
                    "id": 1,
                    "isActive": 1,
                    "order": 1,
                    "wodId": 599450,
                    "exerciseId": 100,
                    "exercise": {
                        "id": 100,
                        "name": "Clean strength",
                        "description": "  6 Min EMOM  ",
                        "measuringUnit": {"id": 1, "name": "For Weight - kg", "unit": "kg"},
                    },
                },
            ],
        }
    ],
    "meta": {"currentPage": 1, "lastPage": 1, "perPage": 10, "total": 1},
}


class TestFormatWod:
    def test_basic_structure(self):
        result = format_wod(SAMPLE_WOD_DATA)
        assert len(result) == 1
        wod = result[0]
        assert wod["id"] == 599450
        assert wod["date"] == "2026-03-19"

    def test_whitespace_stripped(self):
        result = format_wod(SAMPLE_WOD_DATA)
        wod = result[0]
        assert wod["warmUp"] == "10 min warm-up"
        assert wod["coolDown"] == "5 min cool-down"
        assert wod["exercises"][0]["description"] == "6 Min EMOM"

    def test_null_fields_become_empty_string(self):
        result = format_wod(SAMPLE_WOD_DATA)
        wod = result[0]
        assert wod["coachNotes"] == ""
        assert wod["memberNotes"] == ""

    def test_exercises_sorted_by_order(self):
        result = format_wod(SAMPLE_WOD_DATA)
        exercises = result[0]["exercises"]
        assert len(exercises) == 2
        assert exercises[0]["order"] == 1
        assert exercises[0]["name"] == "Clean strength"
        assert exercises[1]["order"] == 2
        assert exercises[1]["name"] == "Big bolt"

    def test_measuring_unit_included(self):
        result = format_wod(SAMPLE_WOD_DATA)
        exercises = result[0]["exercises"]
        assert exercises[0]["measuringUnit"] == "For Weight - kg"
        assert exercises[1]["measuringUnit"] == "For Rounds & Reps"

    def test_inactive_exercises_excluded(self):
        data = {
            "data": [
                {
                    **SAMPLE_WOD_DATA["data"][0],
                    "wodExercises": [
                        {**SAMPLE_WOD_DATA["data"][0]["wodExercises"][0], "isActive": 0},
                        SAMPLE_WOD_DATA["data"][0]["wodExercises"][1],
                    ],
                }
            ]
        }
        result = format_wod(data)
        assert len(result[0]["exercises"]) == 1
        assert result[0]["exercises"][0]["name"] == "Clean strength"

    def test_null_warm_up_becomes_empty_string(self):
        data = {"data": [{**SAMPLE_WOD_DATA["data"][0], "warmUp": None}]}
        result = format_wod(data)
        assert result[0]["warmUp"] == ""

    def test_empty_data_returns_empty_list(self):
        assert format_wod({"data": []}) == []

    def test_multiple_wods(self):
        wod2 = {**SAMPLE_WOD_DATA["data"][0], "id": 999, "date": "2026-03-20", "wodExercises": []}
        data = {"data": [SAMPLE_WOD_DATA["data"][0], wod2]}
        result = format_wod(data)
        assert len(result) == 2
        assert result[1]["id"] == 999
