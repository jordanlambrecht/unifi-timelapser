#!/usr/bin/env python3
# src/utils/path_helpers.py
"""
Path and directory utility functions
Centralizes all path operations and directory creation logic.
"""

import os
from pathlib import Path
from typing import Optional, List, Union
import logging

__all__ = [
    "ensure_directory_exists",
    "get_camera_directory",
    "get_camera_subdirectory",
    "initialize_camera_directories",
    "get_timelapse_output_path",
    "list_camera_images",
]


def ensure_directory_exists(
    path: Path, logger: Optional[logging.Logger] = None
) -> bool:
    """
    Ensure directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists
        logger: Optional logger for error reporting

    Returns:
        True if directory exists or was created successfully
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        if logger:
            logger.error(f"Error creating directory {path}: {e}")
        return False


def get_camera_directory(base_path: str, camera_name: str) -> Path:
    """
    Get standardized camera directory path.

    Args:
        base_path: Base storage path
        camera_name: Camera name

    Returns:
        Path to camera directory
    """
    return Path(base_path) / camera_name


def get_camera_subdirectory(base_path: str, camera_name: str, subdir: str) -> Path:
    """
    Get camera subdirectory path (frames, timelapses, etc.).

    Args:
        base_path: Base storage path
        camera_name: Camera name
        subdir: Subdirectory name (frames, timelapses, etc.)

    Returns:
        Path to camera subdirectory
    """
    return get_camera_directory(base_path, camera_name) / subdir


def initialize_camera_directories(
    base_path: str,
    camera_name: str,
    subdirs: Optional[List[str]] = None,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """
    Initialize all necessary directories for a camera.

    Args:
        base_path: Base storage path
        camera_name: Camera name
        subdirs: List of subdirectories to create (default: standard set)
        logger: Optional logger

    Returns:
        True if all directories were created successfully
    """
    if subdirs is None:
        subdirs = [
            "frames",
            "timelapses",
            "checkpoint_timelapses",
            "continuous_timelapses",
        ]

    success = True
    base_camera_dir = get_camera_directory(base_path, camera_name)

    # Create base camera directory
    if not ensure_directory_exists(base_camera_dir, logger):
        return False

    # Create subdirectories
    for subdir in subdirs:
        subdir_path = base_camera_dir / subdir
        if not ensure_directory_exists(subdir_path, logger):
            success = False

    if success and logger:
        logger.debug(f"Initialized directories for camera '{camera_name}'")

    return success


def get_timelapse_output_path(
    base_path: str, camera_name: str, filename: str, is_checkpoint: bool = False
) -> Path:
    """
    Get standardized timelapse output path.

    Args:
        base_path: Base storage path
        camera_name: Camera name
        filename: Timelapse filename
        is_checkpoint: Whether this is a checkpoint timelapse

    Returns:
        Path to timelapse output file
    """
    subdir = "checkpoint_timelapses" if is_checkpoint else "timelapses"
    return get_camera_subdirectory(base_path, camera_name, subdir) / filename


def list_camera_images(
    base_path: str, camera_name: str, pattern: str = "*.jpg", sort_by_time: bool = True
) -> List[Path]:
    """
    List images for a camera.

    Args:
        base_path: Base storage path
        camera_name: Camera name
        pattern: File pattern to match
        sort_by_time: Whether to sort by modification time

    Returns:
        List of image file paths
    """
    frames_dir = get_camera_subdirectory(base_path, camera_name, "frames")

    if not frames_dir.exists():
        return []

    files = list(frames_dir.glob(pattern))

    if sort_by_time:
        files.sort(key=lambda p: p.stat().st_mtime)

    return files
