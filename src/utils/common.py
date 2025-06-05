#!/usr/bin/env python3
# src/utils/common.py
"""
Common utility functions used across the application.
Centralizes frequently used helpers to avoid duplication.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import pytz

from .constants import DEFAULT_TIMEZONE

__all__ = [
    "format_file_size",
    "get_time_ago",
    "safe_divide",
    "ensure_timezone_aware",
    "calculate_next_capture_time",
    "cleanup_old_files",
    "parse_bool_env",
    "get_project_root",
    "get_media_directory",
    "get_logs_directory",
]


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    size_value = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_value < 1024.0:
            return f"{size_value:.2f} {unit}"
        size_value /= 1024.0
    return f"{size_value:.2f} PB"


def get_time_ago(timestamp: datetime) -> str:
    """
    Get human-readable time ago string.

    Args:
        timestamp: Datetime to compare with now

    Returns:
        Human-readable time ago string
    """
    if not timestamp:
        return "Unknown"

    # Handle both naive and aware datetimes
    if timestamp.tzinfo is None:
        now = datetime.now()
    else:
        now = datetime.now(timestamp.tzinfo)

    diff = now - timestamp

    if diff.total_seconds() < 60:
        return "Just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    else:
        days = int(diff.total_seconds() / 86400)
        return f'{days} day{"s" if days != 1 else ""} ago'


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.

    Args:
        numerator: The numerator
        denominator: The denominator
        default: Default value if division by zero

    Returns:
        Result of division or default
    """
    if denominator == 0:
        return default
    return numerator / denominator


def ensure_timezone_aware(
    dt: datetime, timezone_str: str = DEFAULT_TIMEZONE
) -> datetime:
    """
    Ensure a datetime is timezone-aware.

    Args:
        dt: Datetime object (may be naive or aware)
        timezone_str: Timezone string to use if naive

    Returns:
        Timezone-aware datetime
    """
    if dt.tzinfo is None:
        try:
            tz = pytz.timezone(timezone_str)
            return tz.localize(dt)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC.localize(dt)
    return dt


def calculate_next_capture_time(
    last_capture_time: Optional[datetime], capture_interval: int
) -> Tuple[datetime, int]:
    """
    Calculate next capture time and seconds until next capture.

    Args:
        last_capture_time: Last capture datetime
        capture_interval: Capture interval in seconds

    Returns:
        Tuple of (next_capture_time, seconds_until_next_capture)
    """
    if not last_capture_time:
        return datetime.now(), 0

    elapsed_since_last = datetime.now() - last_capture_time
    elapsed_seconds = elapsed_since_last.total_seconds()
    seconds_until_next = max(0, capture_interval - elapsed_seconds)
    next_capture_time = datetime.now() + timedelta(seconds=seconds_until_next)

    return next_capture_time, int(seconds_until_next)


def cleanup_old_files(
    directory: Path,
    days_to_keep: int,
    file_pattern: str,
    timezone: pytz.BaseTzInfo,
    logger: logging.Logger,
    dry_run: bool = False,
) -> int:
    """
    Clean up old files in a directory based on age.
    Single implementation to avoid duplication.

    Args:
        directory: Directory to clean up
        days_to_keep: Number of days to keep files
        file_pattern: Glob pattern for files (e.g., "*.jpg")
        timezone: Timezone for date calculations
        logger: Logger instance
        dry_run: If True, only log what would be deleted

    Returns:
        Number of files deleted (or would be deleted in dry run)
    """
    if days_to_keep <= 0:
        logger.debug(f"Cleanup disabled for {directory} (days_to_keep <= 0)")
        return 0

    if not directory.exists():
        logger.debug(f"Directory {directory} does not exist, skipping cleanup")
        return 0

    cutoff = datetime.now(timezone) - timedelta(days=days_to_keep)
    files_deleted = 0

    try:
        for file_path in directory.glob(file_pattern):
            if file_path.is_file():
                try:
                    file_time = datetime.fromtimestamp(
                        file_path.stat().st_mtime, tz=timezone
                    )
                    if file_time < cutoff:
                        if dry_run:
                            logger.info(f"Would delete old file: {file_path}")
                        else:
                            file_path.unlink()
                            logger.debug(f"Deleted old file: {file_path}")
                        files_deleted += 1
                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")

        if files_deleted > 0:
            action = "Would delete" if dry_run else "Deleted"
            logger.info(f"{action} {files_deleted} old files from {directory}")

        return files_deleted

    except Exception as e:
        logger.error(f"Error during cleanup of {directory}: {e}")
        return 0


def parse_bool_env(env_value: Optional[str], default: bool = False) -> bool:
    """
    Parse boolean environment variable.

    Args:
        env_value: Environment variable value
        default: Default if None or invalid

    Returns:
        Boolean value
    """
    if env_value is None:
        return default

    return env_value.lower() in ("true", "1", "yes", "on", "enabled")


def get_project_root() -> Path:
    """
    Get the project root directory.
    Assumes this file is in src/utils/

    Returns:
        Path to project root
    """
    return Path(__file__).parent.parent.parent


def get_media_directory() -> Path:
    """
    Get the media directory path.

    Returns:
        Path to media directory
    """
    return get_project_root() / "media"


def get_logs_directory() -> Path:
    """
    Get the logs directory path.

    Returns:
        Path to logs directory
    """
    return get_project_root() / "logs"
