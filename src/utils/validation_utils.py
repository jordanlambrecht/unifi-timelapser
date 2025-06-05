#!/usr/bin/env python3
# src/utils/validation_utils.py
"""
Validation utilities for configuration and user input.
Centralizes common validation patterns used throughout the application.
"""

from typing import List, Optional, Tuple
import os
import re
from pathlib import Path
from urllib.parse import urlparse


def validate_directory_path(path: str, create_if_missing: bool = False) -> bool:
    """
    Validate if directory path exists or can be created.

    Args:
        path: Directory path to validate
        create_if_missing: Whether to create the directory if it doesn't exist

    Returns:
        True if valid/accessible, False otherwise
    """
    try:
        path_obj = Path(path)

        if path_obj.exists() and path_obj.is_dir():
            return True

        if create_if_missing:
            path_obj.mkdir(parents=True, exist_ok=True)
            return True

        return False

    except (OSError, PermissionError):
        return False


def validate_file_path(path: str) -> bool:
    """
    Validate if file path exists and is readable.

    Args:
        path: File path to validate

    Returns:
        True if valid file, False otherwise
    """
    try:
        path_obj = Path(path)
        return path_obj.exists() and path_obj.is_file()
    except (OSError, PermissionError):
        return False


def validate_url_format(url: str) -> bool:
    """
    Basic URL validation for camera streams.

    Args:
        url: URL to validate

    Returns:
        True if valid URL format, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    # Check for common camera stream protocols
    valid_schemes = ["http", "https", "rtsp", "rtsps"]

    try:
        parsed = urlparse(url)
        return parsed.scheme.lower() in valid_schemes and parsed.netloc != ""
    except Exception:
        return False


def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
    """
    Validate file has allowed extension.

    Args:
        filename: Filename to check
        allowed_extensions: List of allowed extensions (with or without dots)

    Returns:
        True if extension is allowed, False otherwise
    """
    if not filename or not allowed_extensions:
        return False

    # Normalize extensions to have dots
    normalized_extensions = [
        ext if ext.startswith(".") else f".{ext}" for ext in allowed_extensions
    ]

    file_ext = Path(filename).suffix.lower()
    return file_ext in [ext.lower() for ext in normalized_extensions]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for cross-platform compatibility.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for all platforms
    """
    if not filename:
        return "unnamed"

    # Characters not allowed in filenames on various platforms
    invalid_chars = '<>:"/\\|?*'

    # Replace invalid characters with underscores
    sanitized = "".join(c if c not in invalid_chars else "_" for c in filename)

    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(". ")

    # Ensure we have a valid filename
    return sanitized if sanitized else "unnamed"


def validate_image_dimensions(width: int, height: int) -> bool:
    """
    Validate image dimensions are reasonable.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        True if dimensions are valid, False otherwise
    """
    # Allow 0 (original size) or positive values up to 8K
    if width < 0 or height < 0:
        return False

    if width > 7680 or height > 4320:  # 8K limits
        return False

    # Both must be 0 (original) or both must be positive
    return (width == 0) == (height == 0)


def validate_port_number(port: int) -> bool:
    """
    Validate port number is in valid range.

    Args:
        port: Port number to validate

    Returns:
        True if valid port, False otherwise
    """
    return 1 <= port <= 65535


def validate_email_format(email: str) -> bool:
    """
    Basic email validation using regex.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    if not email or not isinstance(email, str):
        return False

    # Basic email regex pattern
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_camera_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate camera name meets requirements.

    Args:
        name: Camera name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name or not isinstance(name, str):
        return False, "Camera name cannot be empty"

    # Remove whitespace
    name = name.strip()

    if len(name) < 1:
        return False, "Camera name cannot be empty"

    if len(name) > 50:
        return False, "Camera name cannot exceed 50 characters"

    # Check for invalid characters (filesystem unsafe)
    invalid_chars = '<>:"/\\|?*'
    if any(char in name for char in invalid_chars):
        return False, f"Camera name cannot contain: {invalid_chars}"

    # Check for reserved names
    reserved_names = [
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    ]
    if name.lower() in reserved_names:
        return False, f"Camera name '{name}' is reserved and cannot be used"

    return True, None


def validate_positive_integer(
    value: int, min_value: int = 1, max_value: Optional[int] = None
) -> bool:
    """
    Validate value is a positive integer within specified range.

    Args:
        value: Value to validate
        min_value: Minimum allowed value (default: 1)
        max_value: Maximum allowed value (optional)

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(value, int):
        return False

    if value < min_value:
        return False

    if max_value is not None and value > max_value:
        return False

    return True


def validate_percentage(value: int) -> bool:
    """
    Validate value is a valid percentage (0-100).

    Args:
        value: Percentage value to validate

    Returns:
        True if valid percentage, False otherwise
    """
    return validate_positive_integer(value, min_value=0, max_value=100)


def validate_time_format(time_str: str) -> bool:
    """
    Validate time string is in HH:MM format.

    Args:
        time_str: Time string to validate

    Returns:
        True if valid time format, False otherwise
    """
    if not time_str or not isinstance(time_str, str):
        return False

    # Check format with regex
    pattern = r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$"
    return re.match(pattern, time_str) is not None
