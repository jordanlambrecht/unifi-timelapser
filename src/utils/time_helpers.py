#!/usr/bin/env python3
# src/utils/time_helpers.py
"""
Centralized time and timezone utilities for UniFi Timelapser.
Consolidates all time formatting, timezone handling, and time window logic.
"""

import pytz
from datetime import datetime, time
from typing import Union, Optional, Tuple
import logging

__all__ = [
    "parse_timezone",
    "get_current_time_in_tz",
    "format_timestamp",
    "create_timestamped_name",
    "parse_time_window",
    "is_within_time_window",
    "calculate_duration_seconds",
    "format_duration_human_readable",
    "is_same_day",
    "get_day_start",
    "get_day_end",
    "days_between",
]


def parse_timezone(
    timezone_str: str, logger: Optional[logging.Logger] = None
) -> pytz.BaseTzInfo:
    """
    Parse timezone string and return timezone object with error handling.

    Args:
        timezone_str: Timezone string (e.g., "America/Chicago")
        logger: Optional logger for warnings

    Returns:
        Timezone object, defaults to UTC on error
    """
    try:
        return pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        if logger:
            logger.warning(f"Invalid timezone '{timezone_str}', using UTC")
        return pytz.UTC


def get_current_time_in_tz(
    timezone_str: str, logger: Optional[logging.Logger] = None
) -> datetime:
    """
    Get current time in specified timezone.

    Args:
        timezone_str: Timezone string
        logger: Optional logger for warnings

    Returns:
        Current datetime in specified timezone
    """
    tz = parse_timezone(timezone_str, logger)
    return datetime.now(tz)


def format_timestamp(dt: datetime, format_str: str = "%Y%m%d_%H%M%S") -> str:
    """
    Format datetime to string using specified format.

    Args:
        dt: Datetime object
        format_str: Format string (default: YYYYMMDD_HHMMSS for filenames)

    Returns:
        Formatted timestamp string
    """
    return dt.strftime(format_str)


def create_timestamped_name(
    base_name: str,
    timestamp: Optional[datetime] = None,
    timezone_str: str = "UTC",
    extension: str = "",
    logger: Optional[logging.Logger] = None,
) -> str:
    """
    Create a timestamped filename with timezone support.

    Args:
        base_name: Base name (e.g., camera name)
        timestamp: Optional timestamp (defaults to current time)
        timezone_str: Timezone for timestamp localization
        extension: File extension (with or without dot)
        logger: Optional logger for warnings

    Returns:
        Timestamped filename (e.g., "camera1_20240604_143022.jpg")
    """
    if timestamp is None:
        timestamp = get_current_time_in_tz(timezone_str, logger)
    else:
        # Ensure timestamp is in the correct timezone
        tz = parse_timezone(timezone_str, logger)
        timestamp = timestamp.astimezone(tz)

    timestamp_str = format_timestamp(timestamp)

    if extension and not extension.startswith("."):
        extension = f".{extension}"

    return f"{base_name}_{timestamp_str}{extension}"


def parse_time_window(start_str: str, stop_str: str) -> Tuple[time, time]:
    """
    Parse time window strings into time objects.

    Args:
        start_str: Start time string in HH:MM format
        stop_str: Stop time string in HH:MM format

    Returns:
        Tuple of (start_time, stop_time)

    Raises:
        ValueError: If time format is invalid
    """
    try:
        start_time = datetime.strptime(start_str, "%H:%M").time()
        stop_time = datetime.strptime(stop_str, "%H:%M").time()
        return start_time, stop_time
    except ValueError as e:
        raise ValueError(f"Invalid time format: {e}. Expected HH:MM format.")


def is_within_time_window(
    current_time: time, start_time: time, stop_time: time
) -> bool:
    """
    Check if current time is within the specified window.
    Handles windows that cross midnight.

    Args:
        current_time: Current time to check
        start_time: Window start time
        stop_time: Window stop time

    Returns:
        True if within window, False otherwise
    """
    if start_time == stop_time:
        return True  # 24/7 operation (00:00-00:00)
    elif start_time < stop_time:
        # Normal window (e.g., 09:00-17:00)
        return start_time <= current_time <= stop_time
    else:
        # Window crosses midnight (e.g., 22:00-06:00)
        return current_time >= start_time or current_time <= stop_time


def calculate_duration_seconds(start_time: datetime, end_time: datetime) -> float:
    """
    Calculate duration between two datetimes in seconds.

    Args:
        start_time: Start datetime
        end_time: End datetime

    Returns:
        Duration in seconds (can be negative if end < start)
    """
    delta = end_time - start_time
    return delta.total_seconds()


def format_duration_human_readable(seconds: float) -> str:
    """
    Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable duration string (e.g., "2.5m", "1.2h")
    """
    abs_seconds = abs(seconds)

    if abs_seconds < 60:
        return f"{abs_seconds:.1f}s"
    elif abs_seconds < 3600:
        minutes = abs_seconds / 60
        return f"{minutes:.1f}m"
    elif abs_seconds < 86400:
        hours = abs_seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = abs_seconds / 86400
        return f"{days:.1f}d"


def is_same_day(dt1: datetime, dt2: datetime) -> bool:
    """
    Check if two datetimes are on the same day (ignoring time).

    Args:
        dt1: First datetime
        dt2: Second datetime

    Returns:
        True if same day, False otherwise
    """
    return dt1.date() == dt2.date()


def get_day_start(dt: datetime) -> datetime:
    """
    Get the start of the day (00:00:00) for the given datetime.

    Args:
        dt: Input datetime

    Returns:
        Datetime at start of the same day
    """
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_day_end(dt: datetime) -> datetime:
    """
    Get the end of the day (23:59:59.999999) for the given datetime.

    Args:
        dt: Input datetime

    Returns:
        Datetime at end of the same day
    """
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def days_between(start_date: datetime, end_date: datetime) -> int:
    """
    Calculate number of full days between two dates.

    Args:
        start_date: Start datetime
        end_date: End datetime

    Returns:
        Number of days (can be negative if end < start)
    """
    delta = end_date.date() - start_date.date()
    return delta.days
