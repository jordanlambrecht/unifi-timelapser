#!/usr/bin/env python3
# src/services/cleanup_service.py
"""
Cleanup service for UniFi Timelapser.
Handles image and log cleanup operations as business logic.
"""

import logging
from pathlib import Path

from core.config import Config
from utils.time_helpers import parse_timezone
from utils.path_helpers import get_camera_directory
from utils.constants import IMAGE_PATTERNS
from utils.common import cleanup_old_files


class CleanupService:
    """
    Service responsible for cleanup operations.
    Handles image file cleanup and log file cleanup.
    """

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize the cleanup service.

        Args:
            config: Application configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger

    def run_purge_cycle(self) -> None:
        """
        Run a complete purge cycle for all cameras.
        """
        try:
            if not self.config.is_purge_enabled():
                self.logger.debug("Image purge is disabled")
                return

            storage_settings = self.config.get_storage_settings_typed()
            cleanup_days = storage_settings.cleanup_days
            if cleanup_days <= 0:
                self.logger.debug("Image purge days not configured properly")
                return

            camera_configs = self.config.get_cameras_typed()
            if not camera_configs:
                self.logger.debug("No cameras configured for purge")
                return

            output_dir = self.config.get_storage_path()
            if not output_dir:
                self.logger.error("Storage path not configured for purge cycle")
                return

            timezone_str = self.config.get_timezone_str()
            image_settings = self.config.get_image_settings_typed()
            image_type = image_settings.image_type.value
            pattern = IMAGE_PATTERNS.get(image_type, f"*.{image_type}")

            total_deleted = 0
            for camera_config in camera_configs:
                camera_name = camera_config.name
                if not camera_name:
                    continue

                frames_dir = get_camera_directory(output_dir, camera_name) / "frames"
                timezone = parse_timezone(timezone_str, self.logger)
                deleted = cleanup_old_files(
                    directory=frames_dir,
                    days_to_keep=cleanup_days,
                    file_pattern=pattern,
                    timezone=timezone,
                    logger=self.logger,
                )
                total_deleted += deleted

            if total_deleted > 0:
                self.logger.info(
                    f"Purge cycle complete: deleted {total_deleted} old files"
                )

        except Exception as e:
            self.logger.error(f"Error during purge cycle: {e}")

    def run_log_cleanup_cycle(self) -> None:
        """
        Run a log cleanup cycle.
        """
        try:
            log_cleanup_days = self.config.get_log_retention_days()
            if log_cleanup_days <= 0:
                self.logger.debug("Log cleanup is disabled")
                return

            log_dir = self.config.get_log_directory()
            log_path = Path(log_dir)

            if not log_path.exists():
                self.logger.debug(f"Log directory {log_dir} does not exist")
                return

            timezone_str = self.config.get_timezone_str()
            timezone = parse_timezone(timezone_str, self.logger)

            # Use common cleanup function for logs too
            files_deleted = cleanup_old_files(
                directory=log_path,
                days_to_keep=log_cleanup_days,
                file_pattern="*.log",
                timezone=timezone,
                logger=self.logger,
            )

            if files_deleted > 0:
                self.logger.info(
                    f"Log cleanup complete: deleted {files_deleted} old log files"
                )

        except Exception as e:
            self.logger.error(f"Error during log cleanup cycle: {e}")
