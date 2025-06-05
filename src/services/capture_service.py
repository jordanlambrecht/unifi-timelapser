#!/usr/bin/env python3
# src/services/capture_service.py

import logging
from pathlib import Path
from typing import Dict, Optional

from core.config import Config
from core.models import CameraSettings
from utils import image_processing, file_management


class CaptureService:
    """
    Service responsible for capturing images from configured cameras.
    """

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize the CaptureService with dependencies.

        Args:
            config: The application configuration object
            logger: Logger instance
        """
        self.app_config = config
        self.logger = logger

    def capture_image_for_camera(self, camera_config: CameraSettings) -> Optional[Path]:
        """
        Captures an image for a single camera.

        Args:
            camera_config: CameraSettings configuration for the camera.

        Returns:
            Path to the captured image if successful, None otherwise.
        """
        camera_name = camera_config.name
        if not camera_name or not isinstance(camera_name, str):
            self.logger.error("Invalid camera name provided")
            return None

        if not camera_config.enabled:
            self.logger.debug(f"Camera {camera_name} is disabled, skipping capture")
            return None

        snapshot_url = camera_config.url
        if not snapshot_url or not isinstance(snapshot_url, str):
            self.logger.error(f"Invalid snapshot URL for camera {camera_name}")
            return None

        storage_path_str = self.app_config.get_storage_path()
        if not storage_path_str:
            self.logger.error("Storage path not configured")
            return None

        camera_storage_dir = file_management.ensure_camera_storage_exists(
            camera_name, self.app_config, self.logger
        )
        if not camera_storage_dir:
            self.logger.error(
                f"Failed to ensure storage directory for camera {camera_name}"
            )
            return None

        self.logger.info(f"Attempting to capture image for camera: {camera_name}")

        # Get image settings using typed config
        image_settings = self.app_config.get_image_settings_typed()
        # Get rotation from camera configuration
        rotation_degrees = (
            camera_config.rotation.value
        )  # Get rotation from camera config
        image_type = image_settings.image_type.value  # Convert enum to string

        try:
            # Use the frames subdirectory for captured images
            frames_dir = camera_storage_dir / "frames"

            captured_image_path = image_processing.capture_image_from_camera(
                camera_name=camera_name,
                camera_url=snapshot_url,
                output_dir=frames_dir,
                image_type=image_type,
                rotate_option=rotation_degrees,
                logger=self.logger,
                retries=image_settings.image_capture_retries,
                retry_delay=image_settings.image_capture_sleep,
                image_width=image_settings.image_width,
                image_height=image_settings.image_height,
                timezone_str=self.app_config.get_timezone_str(),
                max_image_size=image_settings.max_image_size,
                compression_quality=image_settings.image_compression_quality,
            )

            if captured_image_path:
                self.logger.info(
                    f"Successfully captured image for '{camera_name}' to {captured_image_path}"
                )
                return captured_image_path
            else:
                self.logger.error(
                    f"Failed to capture image for camera '{camera_name}'."
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Exception during image capture for camera '{camera_name}': {e}",
                exc_info=True,
            )
            return None

    def capture_images_for_all_enabled_cameras(self) -> Dict[str, Optional[Path]]:
        """
        Captures images for all enabled cameras as defined in the configuration.

        Returns:
            A dictionary mapping camera names to the Path of the captured image (or None if failed).
        """
        self.logger.info("Starting image capture cycle for all enabled cameras.")
        cameras = self.app_config.get_cameras_typed()
        results: Dict[str, Optional[Path]] = {}

        if not cameras:
            self.logger.warning("No cameras configured. Nothing to capture.")
            return results

        for cam_config in cameras:
            camera_name = cam_config.name
            if not camera_name or not isinstance(camera_name, str):
                self.logger.warning(
                    f"Skipping camera with no or invalid name in configuration: {cam_config}"
                )
                continue

            # is_camera_enabled check is handled within capture_image_for_camera
            # but we can log a summary here or skip earlier
            if self.app_config.is_camera_enabled(camera_name):
                self.logger.debug(f"Processing enabled camera: {camera_name}")
                results[camera_name] = self.capture_image_for_camera(cam_config)
            else:
                self.logger.debug(
                    f"Camera '{camera_name}' is disabled. Skipping its capture cycle."
                )
                results[camera_name] = None  # mark as None for disabled

        self.logger.info("Image capture cycle finished.")
        successful_captures = {
            k: v
            for k, v in results.items()
            if v is not None and self.app_config.is_camera_enabled(k)
        }
        failed_captures = {
            k: v
            for k, v in results.items()
            if v is None and self.app_config.is_camera_enabled(k)
        }

        if successful_captures:
            self.logger.info(
                f"Successfully captured images for: {list(successful_captures.keys())}"
            )
        if failed_captures:
            self.logger.warning(
                f"Failed to capture images for: {list(failed_captures.keys())}"
            )

        return results
