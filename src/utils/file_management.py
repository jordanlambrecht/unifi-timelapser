#!/usr/bin/env python3
# src/utils/file_management.py
"""
File management utilities for UniFi Timelapser.
Provides utility functions for managing files and directories with dependency injection support.
"""

import logging
from pathlib import Path
from typing import Optional

from core.config import Config
from .path_helpers import initialize_camera_directories, get_camera_directory
from .constants import CAMERA_SUBDIRS


def ensure_camera_storage_exists(
    camera_name: str, config: Config, logger: logging.Logger
) -> Optional[Path]:
    """
    Ensure that the base storage directory for a given camera exists.

    Args:
        camera_name: Name of the camera
        config: Application configuration
        logger: Logger instance

    Returns:
        Path to the camera frames directory if successful, None otherwise
    """
    try:
        output_dir = config.get_storage_path()
        if not output_dir:
            logger.error("Storage path not configured")
            return None

        # Use centralized directory initialization
        success = initialize_camera_directories(
            output_dir, camera_name, CAMERA_SUBDIRS, logger
        )
        if not success:
            return None

        # Return frames directory (most commonly used)
        frames_dir = get_camera_directory(output_dir, camera_name) / "frames"
        logger.debug(
            f"Ensured camera storage exists for '{camera_name}' at {frames_dir}"
        )
        return frames_dir

    except Exception as e:
        logger.error(f"Error creating camera storage for '{camera_name}': {e}")
        return None


def initialize_all_camera_storage(config: Config, logger: logging.Logger) -> None:
    """
    Initialize base storage directories for all configured cameras.

    Args:
        config: Application configuration
        logger: Logger instance
    """
    try:
        camera_configs = config.get_cameras_typed()
        success_count = 0

        for camera_config in camera_configs:
            camera_name = camera_config.name
            if camera_name:
                if ensure_camera_storage_exists(camera_name, config, logger):
                    success_count += 1

        logger.info(
            f"Initialized storage for {success_count}/{len(camera_configs)} cameras"
        )

    except Exception as e:
        logger.error(f"Error initializing camera storage: {e}")
