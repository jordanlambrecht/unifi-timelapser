#!/usr/bin/env python3
# src/services/timelapse_orchestrator_service.py
import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from core.config import Config
from utils.time_helpers import parse_time_window, is_within_time_window
from core.models import TimelapseGenerationMode, TimelapseState
from services.camera_manager import CameraManager
from services.timelapse_service import TimelapseService


class TimelapseOrchestratorService:
    """
    Service that orchestrates the entire timelapse process.
    """

    def __init__(
        self,
        config: Config,
        camera_manager: CameraManager,
        timelapse_service: TimelapseService,
        logger: logging.Logger,
    ) -> None:
        """
        Initialize the orchestrator with dependencies.

        Args:
            config: The application configuration
            camera_manager: Service for camera operations and state management
            timelapse_service: Service for creating timelapses
            logger: Logger instance
        """
        self.config = config
        self.camera_manager = camera_manager
        self.timelapse_service = timelapse_service
        self.logger = logger

        # Track last timelapse generation time for periodic mode
        self._last_timelapse_generation: Dict[str, datetime] = {}
        self._last_continuous_cleanup: Optional[datetime] = None

    def _should_generate_timelapse(self, camera_name: str, timelapse_settings) -> bool:
        """
        Determine if a timelapse should be generated for the given camera based on the generation mode.

        Args:
            camera_name: Name of the camera
            timelapse_settings: Timelapse settings from config

        Returns:
            True if timelapse should be generated, False otherwise
        """
        if not timelapse_settings.timelapse_enabled:
            return False

        # Always generate for manual_only mode (controlled externally)
        if (
            timelapse_settings.timelapse_generation_mode
            == TimelapseGenerationMode.MANUAL_ONLY
        ):
            return False

        # Always generate for every_capture mode
        if (
            timelapse_settings.timelapse_generation_mode
            == TimelapseGenerationMode.EVERY_CAPTURE
        ):
            return True

        # For periodic mode, check if enough time has passed
        if (
            timelapse_settings.timelapse_generation_mode
            == TimelapseGenerationMode.PERIODIC
        ):
            current_time = datetime.now()
            last_generation = self._last_timelapse_generation.get(camera_name)

            if last_generation is None:
                # First time generating for this camera
                self._last_timelapse_generation[camera_name] = current_time
                return True

            time_since_last = current_time - last_generation
            if (
                time_since_last.total_seconds()
                >= timelapse_settings.timelapse_generation_frequency
            ):
                self._last_timelapse_generation[camera_name] = current_time
                return True

        return False

    def _get_cameras_for_capture(self) -> Dict[str, bool]:
        """
        Get cameras that should be captured based on their timelapse state.

        Returns:
            Dictionary mapping camera names to whether they should be captured
        """
        cameras = self.config.get_cameras_typed()
        capture_cameras = {}

        for camera in cameras:
            if not camera.enabled or not camera.name:
                continue

            # Get the timelapse state for this camera
            timelapse_state = self.camera_manager.get_timelapse_state(camera.name)

            # Only capture if timelapse is running
            should_capture = timelapse_state == TimelapseState.RUNNING
            capture_cameras[camera.name] = should_capture

            if not should_capture:
                state_name = timelapse_state.value if timelapse_state else "unknown"
                self.logger.debug(
                    f"Skipping capture for camera '{camera.name}' - timelapse state: {state_name}"
                )

        return capture_cameras

    def _cleanup_old_continuous_timelapses(self) -> None:
        """
        Clean up old continuous timelapses based on max age configuration.
        """
        timelapse_settings = self.config.get_timelapse_settings_typed()

        # Only cleanup if max age is configured (> 0)
        if timelapse_settings.continuous_timelapse_max_age_hours <= 0:
            return

        # Run cleanup at most once per hour
        current_time = datetime.now()
        if (
            self._last_continuous_cleanup
            and (current_time - self._last_continuous_cleanup).total_seconds() < 3600
        ):
            return

        self._last_continuous_cleanup = current_time
        cutoff_time = current_time - timedelta(
            hours=timelapse_settings.continuous_timelapse_max_age_hours
        )

        storage_path_str = self.config.get_storage_path()
        if not storage_path_str:
            return

        base_output_dir = Path(storage_path_str)
        cameras = self.config.get_cameras_typed()

        for camera_conf in cameras:
            if not camera_conf.name:
                continue

            continuous_timelapses_dir = (
                base_output_dir / camera_conf.name / "continuous_timelapses"
            )
            if not continuous_timelapses_dir.exists():
                continue

            try:
                for timelapse_file in continuous_timelapses_dir.glob(
                    f"{camera_conf.name}_timelapse*"
                ):
                    if timelapse_file.is_file():
                        file_time = datetime.fromtimestamp(
                            timelapse_file.stat().st_mtime
                        )
                        if file_time < cutoff_time:
                            timelapse_file.unlink()
                            self.logger.info(
                                f"Cleaned up old continuous timelapse: {timelapse_file}"
                            )
            except Exception as e:
                self.logger.error(
                    f"Error cleaning up continuous timelapses for {camera_conf.name}: {e}"
                )

    def run_timelapser(self, shutdown_flag: Optional[threading.Event] = None) -> None:
        """Main orchestrator loop."""
        self.logger.info("Timelapse orchestrator service started.")

        while not (shutdown_flag and shutdown_flag.is_set()):
            try:
                tz = self.config.get_timezone()
                current_time = datetime.now(tz).time()
                operational_settings = self.config.get_operational_settings_typed()
                timelapse_settings = self.config.get_timelapse_settings_typed()
                # image_settings = self.config.get_image_settings_typed()

                time_start_str = operational_settings.time_start
                time_stop_str = operational_settings.time_stop
                frequency = self.config.get_capture_interval()

                # Parse time window using centralized helper
                try:
                    time_start, time_stop = parse_time_window(
                        time_start_str, time_stop_str
                    )
                except ValueError as e:
                    self.logger.error(
                        f"Invalid time format for timelapse window: {e}. Using 00:00-00:00"
                    )
                    time_start, time_stop = parse_time_window("00:00", "00:00")

                cameras = self.config.get_cameras_typed()
                if not cameras:
                    self.logger.warning("No cameras configured. Orchestrator sleeping.")
                    if shutdown_flag and shutdown_flag.wait(frequency):
                        break
                    elif not shutdown_flag:
                        time.sleep(frequency)
                    continue

                # Check if within time window using centralized helper
                within_time_window = is_within_time_window(
                    current_time, time_start, time_stop
                )

                if within_time_window:
                    self.logger.info(
                        "Within configured time window. Starting capture cycle."
                    )

                    # Get cameras that should be captured based on timelapse state
                    cameras_for_capture = self._get_cameras_for_capture()
                    active_cameras = [
                        name
                        for name, should_capture in cameras_for_capture.items()
                        if should_capture
                    ]

                    if not active_cameras:
                        self.logger.info(
                            "No cameras with active timelapse states. Skipping capture cycle."
                        )
                        capture_results = {}
                    else:
                        self.logger.info(
                            f"Capturing from {len(active_cameras)} cameras with active timelapse states"
                        )
                        # Use CameraManager to capture all cameras concurrently
                        capture_results = self.camera_manager.capture_all_cameras_sync()

                        # Filter results to only include cameras that should be captured
                        capture_results = {
                            name: path
                            for name, path in capture_results.items()
                            if name in active_cameras
                        }

                    # Process results and create timelapses for successful captures
                    for camera_name, captured_image_path in capture_results.items():
                        # Get camera config to check timelapse settings
                        camera_config = self.camera_manager.get_camera_config(
                            camera_name
                        )
                        if not camera_config:
                            continue

                        # Check if timelapse should be generated based on generation mode and state
                        should_generate = self._should_generate_timelapse(
                            camera_name, timelapse_settings
                        )

                        # Additional check: only generate if timelapse is actually running
                        timelapse_state = self.camera_manager.get_timelapse_state(
                            camera_name
                        )
                        is_timelapse_active = timelapse_state == TimelapseState.RUNNING

                        try:
                            if (
                                captured_image_path
                                and should_generate
                                and is_timelapse_active
                            ):
                                self.logger.info(
                                    f"Generating timelapse for {camera_name} (mode: {timelapse_settings.timelapse_generation_mode})"
                                )
                                self.timelapse_service.create_timelapse(
                                    camera_name=camera_name,
                                )
                            elif (
                                not captured_image_path
                                and self.config.is_camera_enabled(camera_name)
                                and timelapse_settings.timelapse_enabled
                                and is_timelapse_active
                            ):
                                self.logger.warning(
                                    f"Timelapse skipped for enabled camera '{camera_name}' because image capture failed."
                                )
                            elif (
                                not should_generate
                                and self.config.is_camera_enabled(camera_name)
                                and timelapse_settings.timelapse_enabled
                                and timelapse_settings.timelapse_generation_mode
                                == TimelapseGenerationMode.PERIODIC
                                and is_timelapse_active
                            ):
                                self.logger.debug(
                                    f"Timelapse generation skipped for camera '{camera_name}' - not yet time for periodic generation."
                                )
                            elif not is_timelapse_active:
                                self.logger.debug(
                                    f"Timelapse generation skipped for camera '{camera_name}' - timelapse not active (state: {timelapse_state.value if timelapse_state else 'unknown'})"
                                )
                            elif (
                                not timelapse_settings.timelapse_enabled
                                and self.config.is_camera_enabled(camera_name)
                            ):
                                self.logger.debug(
                                    f"Timelapse creation is disabled for camera '{camera_name}'. Skipping video creation."
                                )
                        except Exception as e:
                            self.logger.error(
                                f"Error processing camera {camera_name}: {e}",
                                exc_info=True,
                            )

                    # Cleanup old continuous timelapses
                    self._cleanup_old_continuous_timelapses()

                    self.logger.info("Image capture cycle complete.")

                    # Log camera health summary
                    unhealthy_cameras = self.camera_manager.get_unhealthy_cameras()
                    if unhealthy_cameras:
                        self.logger.warning(
                            f"Unhealthy cameras detected: {unhealthy_cameras}"
                        )
                else:
                    self.logger.info(
                        f"Outside time window ({time_start_str}-{time_stop_str}). Sleeping."
                    )

                # Check for checkpoint timelapse creation
                now = datetime.now(tz)
                timelapse_settings_typed = self.config.get_timelapse_settings_typed()
                if (
                    timelapse_settings_typed.checkpoint_enabled
                    and now.hour == 23  # Default checkpoint hour
                    and now.minute == 59  # Default checkpoint minute
                ):
                    self.logger.info("Starting daily checkpoint timelapse creation.")

                    storage_path_str = self.config.get_storage_path()
                    if not storage_path_str:
                        self.logger.error("Storage path not set. Skipping checkpoint.")
                    else:
                        # base_output_dir = Path(storage_path_str)
                        for camera_conf in cameras:
                            camera_name = camera_conf.name
                            if not camera_name or not camera_conf.enabled:
                                continue

                            if not timelapse_settings_typed.timelapse_enabled:
                                self.logger.debug(
                                    f"Timelapse disabled for {camera_name}, skipping checkpoint."
                                )
                                continue

                            self.logger.debug(
                                f"Checkpoint timelapse for camera: {camera_name}"
                            )
                            try:
                                self.timelapse_service.create_timelapse(
                                    camera_name=camera_name,
                                    checkpoint=True,
                                )
                            except Exception as e:
                                self.logger.error(
                                    f"Checkpoint error for {camera_name}: {e}",
                                    exc_info=True,
                                )

                    self.logger.info(
                        "Daily checkpoint timelapse creation complete. Sleeping 60s."
                    )
                    if shutdown_flag:
                        # More responsive shutdown during checkpoint sleep
                        for _ in range(6):  # 6 chunks of 10 seconds = 60 seconds
                            if shutdown_flag.wait(10):
                                return  # Exit immediately if shutdown requested
                    else:
                        time.sleep(60)

                self.logger.debug(f"Orchestrator loop finished. Sleeping {frequency}s.")
                if shutdown_flag:
                    # Break sleep into smaller chunks to check shutdown more frequently
                    sleep_chunks = max(
                        1, frequency // 10
                    )  # Check 10 times during the sleep period, minimum 1 second
                    remaining_sleep = frequency
                    while remaining_sleep > 0:
                        chunk_sleep = min(sleep_chunks, remaining_sleep)
                        if shutdown_flag.wait(chunk_sleep):
                            return  # Exit immediately if shutdown requested
                        remaining_sleep -= chunk_sleep
                else:
                    time.sleep(frequency)

            except Exception as e:
                self.logger.exception(
                    f"Unexpected error in timelapse orchestrator: {e}"
                )
                if shutdown_flag:

                    for _ in range(6):  # 6 chunks of 10 seconds = 60 seconds
                        if shutdown_flag.wait(10):
                            return  # Exit immediately if shutdown requested
                else:
                    time.sleep(60)
