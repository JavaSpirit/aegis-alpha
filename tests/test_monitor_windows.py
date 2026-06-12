"""
Tests for monitor_windows_from_config and is_in_monitor_window (Task 6.1).
TDD RED phase — these tests MUST FAIL before implementation.
"""
from __future__ import annotations

import pytest

from aegis_alpha.runner import (
    DEFAULT_MONITOR_WINDOWS,
    is_in_monitor_window,
    monitor_windows_from_config,
)


# ---------------------------------------------------------------------------
# monitor_windows_from_config
# ---------------------------------------------------------------------------

class TestMonitorWindowsFromConfig:
    def test_empty_config_returns_defaults(self) -> None:
        result = monitor_windows_from_config({})
        assert result == DEFAULT_MONITOR_WINDOWS

    def test_none_monitor_windows_returns_defaults(self) -> None:
        result = monitor_windows_from_config({"monitor_windows": None})
        assert result == DEFAULT_MONITOR_WINDOWS

    def test_empty_list_returns_defaults(self) -> None:
        result = monitor_windows_from_config({"monitor_windows": []})
        assert result == DEFAULT_MONITOR_WINDOWS

    def test_single_custom_window(self) -> None:
        custom = [{"name": "x", "start": "10:00", "end": "10:05"}]
        result = monitor_windows_from_config({"monitor_windows": custom})
        assert result == custom

    def test_multiple_custom_windows(self) -> None:
        custom = [
            {"name": "a", "start": "09:30", "end": "09:45"},
            {"name": "b", "start": "14:00", "end": "14:30"},
        ]
        result = monitor_windows_from_config({"monitor_windows": custom})
        assert result == custom

    def test_returns_new_list_not_mutating_defaults(self) -> None:
        result = monitor_windows_from_config({})
        result.append({"name": "extra", "start": "00:00", "end": "00:01"})
        # DEFAULT_MONITOR_WINDOWS must remain unchanged
        assert len(DEFAULT_MONITOR_WINDOWS) == 2

    def test_malformed_items_skipped(self) -> None:
        """Items missing required keys are dropped; only valid ones kept."""
        windows = [
            {"name": "ok", "start": "09:30", "end": "09:50"},
            {"name": "bad_no_end", "start": "10:00"},
            {"start": "11:00", "end": "11:30"},  # missing name
        ]
        result = monitor_windows_from_config({"monitor_windows": windows})
        assert result == [{"name": "ok", "start": "09:30", "end": "09:50"}]

    def test_all_malformed_falls_back_to_defaults(self) -> None:
        """If all items are malformed, fall back to defaults."""
        windows = [{"name": "bad_no_start", "end": "10:00"}]
        result = monitor_windows_from_config({"monitor_windows": windows})
        assert result == DEFAULT_MONITOR_WINDOWS


# ---------------------------------------------------------------------------
# is_in_monitor_window — boundary tests against defaults
# ---------------------------------------------------------------------------

class TestIsInMonitorWindow:
    """All tests use the default two windows:
       open_drive:   [09:30, 09:50)
       late_morning: [11:10, 11:30)
    """

    @pytest.fixture
    def windows(self) -> list[dict[str, str]]:
        return list(DEFAULT_MONITOR_WINDOWS)

    def test_before_open_drive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("09:29", windows) is None

    def test_start_of_open_drive_inclusive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("09:30", windows) == "open_drive"

    def test_inside_open_drive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("09:49", windows) == "open_drive"

    def test_end_of_open_drive_exclusive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("09:50", windows) is None

    def test_gap_between_windows(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("10:00", windows) is None

    def test_before_late_morning(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("11:09", windows) is None

    def test_start_of_late_morning_inclusive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("11:10", windows) == "late_morning"

    def test_inside_late_morning(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("11:29", windows) == "late_morning"

    def test_end_of_late_morning_exclusive(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("11:30", windows) is None

    def test_empty_windows_returns_none(self) -> None:
        assert is_in_monitor_window("09:35", []) is None

    # --- malformed now_hhmm ---
    def test_empty_string_returns_none(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("", windows) is None

    def test_single_digit_returns_none(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("9", windows) is None

    def test_invalid_time_returns_none(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("25:99", windows) is None

    def test_no_colon_returns_none(self, windows: list[dict[str, str]]) -> None:
        assert is_in_monitor_window("0930", windows) is None
