#!/usr/bin/env python3
# src/services/timelapse_service.py
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from core.config import Config
from core.models import CameraSettings
from utils.ffmpeg_helpers import (
    get_rotation_filter,
    build_timelapse_command,
    log_ffmpeg_command,
)
from utils import path_helpers


class TimelapseService:
    """
    Service responsible for creating timelapse videos from captured images.
    """

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize the TimelapseService with dependencies.

        Args:
            config: The application configuration object
            logger: Logger instance
        """
        self.config = config
        self.logger = logger

    def create_timelapse(
        self, camera_name: str, checkpoint: bool = False
    ) -> Optional[Path]:
        """
        Creates a timelapse video from captured images for a specific camera.

        Args:
            camera_name: The name of the camera.
            checkpoint: If True, creates a checkpoint timelapse (e.g., with a timestamp).
                        If False, creates a daily timelapse (e.g., with a date stamp).

        Returns:
            The Path object of the created timelapse video, or None on failure.
        """
        camera_conf: Optional[CameraSettings] = self.config.get_camera_by_name_typed(
            camera_name
        )
        if not camera_conf:
            self.logger.error(
                f"Configuration for camera '{camera_name}' not found. Skipping timelapse."
            )
            return None

        timelapse_settings = self.config.get_timelapse_settings_typed()
        if not timelapse_settings.timelapse_enabled:
            self.logger.info(
                f"Timelapse creation is disabled globally. Skipping for camera '{camera_name}'."
            )
            return None

        frame_rate: int = timelapse_settings.timelapse_speed
        # Get image settings
        image_settings = self.config.get_image_settings_typed()

        image_type: str = image_settings.image_type.value  # Convert enum to string

        timelapse_format: str = (
            timelapse_settings.timelapse_format.value
        )  # Convert enum to string
        timelapse_speed_multiplier: int = (
            1  # Default speed multiplier (not in current model)
        )
        ffmpeg_preset: str = "medium"  # Default preset (not in current model)
        ffmpeg_crf: str = "23"  # Default CRF (not in current model)

        storage_path_str: Optional[str] = self.config.get_storage_path()
        if not storage_path_str:
            self.logger.error("Storage path not configured. Cannot create timelapse.")
            return None

        base_storage_dir = Path(storage_path_str)
        camera_dir = base_storage_dir / camera_name
        frames_dir = camera_dir / "frames"

        timelapse_output_dir_name: str = "timelapses"  # Default output path segment
        timelapse_subdir = camera_dir / timelapse_output_dir_name

        # Use helper utility to ensure directory exists
        if not path_helpers.ensure_directory_exists(timelapse_subdir, self.logger):
            self.logger.error(f"Error creating timelapse directory {timelapse_subdir}")
            return None

        try:
            tz = self.config.get_timezone()
            current_time = datetime.now(tz)
        except Exception as e:
            self.logger.warning(
                f"Could not get timezone from config ({e}), using naive local time for timelapse filename."
            )
            current_time = datetime.now()

        timestamp_str = current_time.strftime("%Y%m%d_%H%M%S")
        date_str = current_time.strftime("%Y%m%d")

        if checkpoint:
            output_filename = (
                f"{camera_name}_timelapse_checkpoint_{timestamp_str}.{timelapse_format}"
            )
        else:
            output_filename = (
                f"{camera_name}_timelapse_daily_{date_str}.{timelapse_format}"
            )

        output_path = timelapse_subdir / output_filename

        # Verify frames exist
        existing_frames: List[Path] = sorted(
            list(frames_dir.glob(f"{camera_name}_*.{image_type}"))
        )

        if not existing_frames:
            self.logger.warning(
                f"No images found in '{frames_dir}' matching pattern '{camera_name}_*.{image_type}' for {camera_name}. Skipping timelapse."
            )
            return None

        self.logger.info(
            f"Found {len(existing_frames)} frames for timelapse '{camera_name}' using pattern '{camera_name}_*.{image_type}'."
        )

        # Calculate frame rate adjustment based on speed multiplier
        adjusted_frame_rate = frame_rate * timelapse_speed_multiplier

        # Get rotation filter - currently None (could be added to camera settings)
        rotate_filter_str = get_rotation_filter(None)

        # Build ffmpeg command using standardized helper
        input_pattern = str(frames_dir / f"{camera_name}_*.{image_type}")
        ffmpeg_command = build_timelapse_command(
            input_pattern=input_pattern,
            output_path=str(output_path),
            framerate=adjusted_frame_rate,
            preset=ffmpeg_preset,
            crf=ffmpeg_crf,
            rotation_filter=rotate_filter_str,
        )

        try:
            log_ffmpeg_command(ffmpeg_command, self.logger, camera_name)

            process = subprocess.Popen(
                ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.logger.info(f"Successfully created timelapse: {output_path}")
                return output_path
            else:
                self.logger.error(
                    f"FFmpeg failed to create timelapse for '{camera_name}'."
                )
                self.logger.error(
                    f"FFmpeg stdout: {stdout.decode('utf-8', errors='ignore')}"
                )
                self.logger.error(
                    f"FFmpeg stderr: {stderr.decode('utf-8', errors='ignore')}"
                )
                return None

        except FileNotFoundError:
            self.logger.error(
                "FFmpeg not found. Please ensure FFmpeg is installed and in your system's PATH."
            )
            return None
        except Exception as e:
            self.logger.exception(
                f"An unexpected error occurred during timelapse creation for '{camera_name}': {e}"
            )
            return None
