#!/usr/bin/env python3
# src/core/config.py
"""
Configuration management for UniFi Timelapser.
Loads configuration from YAML file with Pydantic validation.
"""

import os
import threading
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
import pytz

from .models import (
    UniFiTimelapserConfig,
    validate_config_data,
    CameraSettings,
    TimelapseSettings,
    ImageSettings,
    StorageSettings,
    OperationalSettings,
    WebDashboardSettings,
)


def _get_logger():
    """Get logger for config module - uses module-level logger to avoid circular imports."""
    return logging.getLogger(__name__)


class Config:
    """
    Configuration manager with dependency injection support.
    - Loads YAML config with environment variable overrides
    - Pydantic validation for type safety
    - Simple reload_config() method when needed
    """

    def __init__(self, config_file_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_file_path: Path to config file, defaults to CONFIG_FILE_PATH env var or "config.yaml"
        """
        self._config_file_path = config_file_path or os.getenv(
            "CONFIG_FILE_PATH", "config.yaml"
        )
        self._config_data: Dict[str, Any] = {}
        self._validated_config: Optional[UniFiTimelapserConfig] = None
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file and environment variables."""
        config_data: Dict[str, Any] = {}

        # Load from YAML file if it exists
        if os.path.exists(self._config_file_path):
            try:
                with open(self._config_file_path, "r") as file:
                    config_data = yaml.safe_load(file) or {}
                _get_logger().info(
                    f"Loaded configuration from {self._config_file_path}"
                )
            except Exception as e:
                _get_logger().error(
                    f"Error loading config file {self._config_file_path}: {e}"
                )
                config_data = {}
        else:
            _get_logger().warning(
                f"Config file {self._config_file_path} not found, using environment variables only"
            )

        # Override with environment variables (map to nested structure)
        storage_settings = config_data.setdefault("storage_settings", {})
        operational_settings = config_data.setdefault("operational_settings", {})
        image_settings = config_data.setdefault("image_settings", {})
        timelapse_settings = config_data.setdefault("timelapse_settings", {})

        env_mappings = {
            "OUTPUT_DIR": ("storage_settings", "output_dir"),
            "CLEANUP_DAYS": ("storage_settings", "cleanup_days"),
            "LOG_CLEANUP_DAYS": ("storage_settings", "log_cleanup_days"),
            "FREQUENCY": ("operational_settings", "frequency"),
            "TIME_START": ("operational_settings", "time_start"),
            "TIME_STOP": ("operational_settings", "time_stop"),
            "TIMEZONE": ("operational_settings", "timezone"),
            "IMAGE_TYPE": ("image_settings", "image_type"),
            "TIMELAPSE_ENABLED": ("timelapse_settings", "timelapse_enabled"),
            "TIMELAPSE_GENERATION_FREQUENCY": (
                "timelapse_settings",
                "timelapse_generation_frequency",
            ),
            "TIMELAPSE_GENERATION_MODE": (
                "timelapse_settings",
                "timelapse_generation_mode",
            ),
            "CONTINUOUS_TIMELAPSE_MAX_AGE_HOURS": (
                "timelapse_settings",
                "continuous_timelapse_max_age_hours",
            ),
        }

        for env_var, (section, key) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert boolean strings
                if env_value.lower() in ("true", "false"):
                    env_value = env_value.lower() == "true"
                # Convert numeric strings
                elif env_value.isdigit():
                    env_value = int(env_value)

                config_data[section][key] = env_value

        self._config_data = config_data

        # Validate with Pydantic
        try:
            self._validated_config = validate_config_data(config_data)
            _get_logger().info("Configuration validation successful")
        except Exception as e:
            _get_logger().error(f"Configuration validation failed: {e}")
            self._validated_config = None

    def reload_config(self) -> None:
        """Reload configuration from file and environment variables."""
        _get_logger().info("Reloading configuration...")
        with self._lock:
            self._load_config()

    def is_config_valid(self) -> bool:
        """Check if configuration passed validation."""
        return self._validated_config is not None

    def get_validated_config(self) -> Optional[UniFiTimelapserConfig]:
        """Get the validated Pydantic configuration model."""
        return self._validated_config

    def get_validation_errors(self) -> List[str]:
        """Get validation errors if any."""
        if self.is_config_valid():
            return []

        try:
            validate_config_data(self._config_data)
            return []
        except Exception as e:
            return [str(e)]

    def get_capture_interval(self) -> int:
        """Get image capture frequency in seconds."""
        if self._validated_config:
            return self._validated_config.operational_settings.frequency
        return 900

    def get_storage_path(self) -> Optional[str]:
        """Get base storage directory path."""
        if self._validated_config:
            return self._validated_config.storage_settings.output_dir
        return None

    def get_timezone_str(self) -> str:
        """Get timezone string."""
        if self._validated_config:
            return self._validated_config.operational_settings.timezone
        return "UTC"

    def get_timezone(self) -> pytz.BaseTzInfo:
        """Get timezone object."""
        try:
            return pytz.timezone(self.get_timezone_str())
        except pytz.UnknownTimeZoneError:
            _get_logger().warning(
                f"Unknown timezone {self.get_timezone_str()}, using UTC"
            )
            return pytz.UTC

    def is_camera_enabled(self, camera_name: str) -> bool:
        """Check if a camera is enabled."""
        cameras = self.get_cameras_typed()
        for camera in cameras:
            if camera.name == camera_name:
                return camera.enabled
        return False

    def is_purge_enabled(self) -> bool:
        """Check if purge (cleanup) is enabled."""
        if self._validated_config:
            cleanup_days = self._validated_config.storage_settings.cleanup_days
            return cleanup_days > 0
        return False

    def get_logging_settings(self) -> Dict[str, Any]:
        """Get logging settings."""
        if self._validated_config:
            log_cleanup_days = self._validated_config.storage_settings.log_cleanup_days
            return {
                "log_cleanup_enabled": log_cleanup_days > 0,
                "log_cleanup_days": log_cleanup_days,
                "log_level": "INFO",  # Default log level
            }
        return {
            "log_cleanup_enabled": False,
            "log_cleanup_days": 0,
            "log_level": "INFO",
        }

    def get_log_file_path(self) -> str:
        """Get log file path."""
        if self._validated_config:
            log_dir = self._validated_config.storage_settings.log_dir
            log_file = self._validated_config.storage_settings.log_file
            return f"{log_dir.rstrip('/')}/{log_file}"
        return "logs/unifi_timelapser.log"  # Default log path

    def get_log_directory(self) -> str:
        """Get log directory path."""
        if self._validated_config:
            return self._validated_config.storage_settings.log_dir
        return "logs"  # Default log directory

    def get_log_retention_days(self) -> int:
        """Get log retention days from logging settings."""
        logging_settings = self.get_logging_settings()
        return logging_settings.get("log_cleanup_days", 0)

    # TYPE-SAFE METHODS RETURNING PYDANTIC MODELS

    def get_cameras_typed(self) -> List[CameraSettings]:
        """Get list of camera configurations as typed Pydantic models."""
        if self._validated_config:
            return self._validated_config.cameras
        return []

    def get_timelapse_settings_typed(self) -> TimelapseSettings:
        """Get timelapse settings as typed Pydantic model."""
        if self._validated_config:
            return self._validated_config.timelapse_settings
        return TimelapseSettings()

    def get_image_settings_typed(self) -> ImageSettings:
        """Get image settings as typed Pydantic model."""
        if self._validated_config:
            return self._validated_config.image_settings
        return ImageSettings()

    def get_storage_settings_typed(self) -> StorageSettings:
        """Get storage settings as typed Pydantic model."""
        if self._validated_config:
            return self._validated_config.storage_settings
        return StorageSettings()

    def get_operational_settings_typed(self) -> OperationalSettings:
        """Get operational settings as typed Pydantic model."""
        if self._validated_config:
            return self._validated_config.operational_settings
        return OperationalSettings()

    def get_camera_by_name_typed(self, camera_name: str) -> Optional[CameraSettings]:
        """Get a specific camera configuration by name as typed Pydantic model."""
        cameras = self.get_cameras_typed()
        for camera in cameras:
            if camera.name == camera_name:
                return camera
        return None

    def get_compression_settings(self) -> Dict[str, Any]:
        """Get compression settings from image settings."""
        # Custom instruction test: Python function generated!
        if self._validated_config:
            image_settings = self._validated_config.image_settings
            return {
                "enabled": image_settings.max_image_size > 0,
                "max_size_kb": image_settings.max_image_size,
                "quality": image_settings.image_compression_quality,
                "quality_step": image_settings.image_compress_quality_step,
            }
        return {
            "enabled": False,
            "max_size_kb": 0,
            "quality": 75,
            "quality_step": 5,
        }

    def get_web_dashboard_settings_typed(self) -> WebDashboardSettings:
        """Get web dashboard settings as typed Pydantic model."""
        if self._validated_config:
            return self._validated_config.web_dashboard_settings
        return WebDashboardSettings()


def create_config(config_file_path: Optional[str] = None) -> Config:
    """
    Factory function to create a Config instance.

    Args:
        config_file_path: Path to config file

    Returns:
        Config instance
    """
    return Config(config_file_path)


def shutdown_config_watcher() -> None:
    """Placeholder for compatibility - no watcher to shutdown in simplified version."""
    pass
