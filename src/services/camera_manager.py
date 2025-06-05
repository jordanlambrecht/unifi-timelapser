#!/usr/bin/env python3
# src/services/camera_manager.py
"""
Centralized camera operations and state management.
"""

import logging
import threading
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from core.config import Config
from core.models import CameraSettings
from core.models import CameraStatus, CameraState, TimelapseState
from utils.image_processing import capture_image_from_camera
from utils import file_management


class CameraManager:
    """
    Centralized camera management service.

    Provides:
    - Camera state tracking and health monitoring
    - Concurrent image capture operations
    - Status reporting and error tracking
    - Database integration for persistent state storage
    """

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        database_manager=None,
    ):
        """
        Initialize the Camera Manager.

        Args:
            config: Application configuration
            logger: Logger instance
            database_manager: Database manager for persistent storage
        """
        self.config = config
        self.logger = logger
        self.database_manager = database_manager
        self.shutdown_flag: Optional[threading.Event] = None  # Set externally
        self._camera_states: Dict[str, CameraState] = {}

        # Initialize database services if database is available
        self._db_services = None
        if self.database_manager:
            try:
                from database.database_services import (
                    CameraService,
                    CaptureAttemptService,
                    ImageService,
                    TimelapseBatchService,
                )

                self._db_services = {
                    "camera": CameraService(),
                    "capture": CaptureAttemptService(),
                    "image": ImageService(),
                    "timelapse_batch": TimelapseBatchService(),
                }
                # Track active timelapse batches for each camera
                self._active_timelapse_batches: Dict[str, int] = {}
                self.logger.info("Database services initialized for CameraManager")
            except Exception as e:
                self.logger.warning(f"Failed to initialize database services: {e}")
                self._db_services = None

        self._initialize_cameras()

    def _initialize_cameras(self) -> None:
        """Initialize camera states from configuration and sync with database"""
        cameras = self.config.get_cameras_typed()

        # Initialize camera states from config
        for camera_config in cameras:
            self._camera_states[camera_config.name] = CameraState(
                name=camera_config.name,
                status=CameraStatus.OFFLINE,
                last_capture_time=None,
                consecutive_failures=0,
                total_captures=0,
                last_error=None,
                timelapse_state=TimelapseState.STOPPED,
                timelapse_frame_count=0,
                timelapse_started_at=None,
                timelapse_paused_at=None,
            )

            # Sync camera with database if database services are available
            if self._db_services:
                self._sync_camera_to_database(camera_config)

        # Restore timelapse states from database
        if self._db_services:
            self._restore_timelapse_states_from_database()

        self.logger.info(f"Initialized {len(self._camera_states)} cameras")

    def _sync_camera_to_database(self, camera_config: CameraSettings) -> None:
        """Sync camera configuration with database"""
        try:
            if not self._db_services:
                return

            camera_service = self._db_services["camera"]

            # Create a simple URL hash based on camera name (since actual URL might be sensitive)
            import hashlib

            url_hash = hashlib.sha256(
                f"{camera_config.name}_{camera_config.url}".encode()
            ).hexdigest()[:32]

            # Check if camera exists in database
            existing_camera = camera_service.get_camera_by_name(camera_config.name)

            if not existing_camera:
                # Create new camera record
                camera_service.create_camera(
                    name=camera_config.name,
                    url_hash=url_hash,
                    enabled=camera_config.enabled,
                    rotation=getattr(camera_config, "rotation", "none"),
                )
                self.logger.info(
                    f"Created database record for camera: {camera_config.name}"
                )
            else:
                # Update existing camera record
                camera_service.update_camera(
                    existing_camera.id,
                    enabled=camera_config.enabled,
                    rotation=getattr(camera_config, "rotation", "none"),
                )
                self.logger.debug(
                    f"Updated database record for camera: {camera_config.name}"
                )

        except Exception as e:
            self.logger.error(
                f"Failed to sync camera {camera_config.name} to database: {e}"
            )

    def _restore_timelapse_states_from_database(self) -> None:
        """Restore timelapse states from active batches in database"""
        try:
            if not self._db_services:
                return

            timelapse_service = self._db_services["timelapse_batch"]
            camera_service = self._db_services["camera"]

            # First, clean up stale processing batches for each camera
            total_cleaned = 0
            for camera_name in self._camera_states.keys():
                camera_record = camera_service.get_camera_by_name(camera_name)
                if camera_record:
                    cleaned_count = timelapse_service.cleanup_stale_processing_batches(
                        camera_record.id, batch_type="continuous"
                    )
                    total_cleaned += cleaned_count
                    if cleaned_count > 0:
                        self.logger.info(
                            f"Cleaned up {cleaned_count} stale processing batches for camera {camera_name}"
                        )

            if total_cleaned > 0:
                self.logger.info(f"Total stale batches cleaned up: {total_cleaned}")

            # Get all remaining active (processing) timelapse batches
            active_batches = timelapse_service.get_active_batches()

            for batch in active_batches:
                # Get camera name from camera ID
                camera_record = camera_service.get_camera_by_id(batch.camera_id)
                if not camera_record:
                    self.logger.warning(
                        f"Camera with ID {batch.camera_id} not found for active batch {batch.id}"
                    )
                    continue

                camera_name = camera_record.name

                # Update camera state if we have it
                if camera_name in self._camera_states:
                    state = self._camera_states[camera_name]
                    state.timelapse_state = TimelapseState.RUNNING
                    state.timelapse_started_at = batch.started_at
                    state.timelapse_frame_count = batch.total_frames or 0

                    # Track the active batch
                    self._active_timelapse_batches[camera_name] = batch.id

                    self.logger.info(
                        f"Restored timelapse state for camera {camera_name}: batch {batch.id}, frames {state.timelapse_frame_count}"
                    )
                else:
                    self.logger.warning(
                        f"Camera {camera_name} not found in states for active batch {batch.id}"
                    )

        except Exception as e:
            self.logger.error(f"Failed to restore timelapse states from database: {e}")

    def _log_capture_to_database(
        self,
        camera_name: str,
        success: bool,
        image_path: Optional[Path] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Log capture attempt to database"""
        try:
            if not self._db_services:
                return

            camera_service = self._db_services["camera"]
            capture_service = self._db_services["capture"]

            # Get camera ID from database
            camera_record = camera_service.get_camera_by_name(camera_name)
            if not camera_record:
                self.logger.warning(
                    f"Camera {camera_name} not found in database for capture logging"
                )
                return

            camera_id = camera_record.id
            image_id = None

            # If successful and we have an image path, create image record
            if success and image_path:
                image_id = self._create_image_record(camera_id, image_path)

            # Create capture attempt record
            status = "success" if success else "failed"
            capture_service.create_attempt(
                camera_id=camera_id,
                status=status,
                image_id=image_id,
                error_message=error_message,
                duration_ms=duration_ms,
                retry_count=0,  # TODO: We need to enhance this later to track retries
            )

            self.logger.debug(f"Logged capture attempt for {camera_name}: {status}")

        except Exception as e:
            self.logger.error(
                f"Failed to log capture attempt to database for {camera_name}: {e}"
            )

    def _create_image_record(self, camera_id: int, image_path: Path) -> Optional[int]:
        """Create an image record in the database"""
        try:
            if not self._db_services or not image_path.exists():
                return None

            image_service = self._db_services["image"]

            # Get image file information
            file_size = image_path.stat().st_size
            file_format = image_path.suffix.lower().lstrip(".")

            # Create image record
            image_record = image_service.create_image(
                camera_id=camera_id,
                filename=image_path.name,
                file_path=str(image_path),
                file_size_bytes=file_size,
                format=file_format,
                captured_at=datetime.now(),
            )

            return image_record.id

        except Exception as e:
            self.logger.error(f"Failed to create image record: {e}")
            return None

    def _start_timelapse_batch(self, camera_name: str) -> None:
        """Create a new timelapse batch in the database"""
        try:
            if not self._db_services:
                return

            camera_service = self._db_services["camera"]
            timelapse_service = self._db_services["timelapse_batch"]

            # Get camera ID from database
            camera_record = camera_service.get_camera_by_name(camera_name)
            if not camera_record:
                self.logger.warning(
                    f"Camera {camera_name} not found in database for timelapse batch"
                )
                return

            # Create new timelapse batch
            batch = timelapse_service.create_batch(
                camera_id=camera_record.id,
                batch_type="continuous",
                generation_mode="every_capture",
                status="processing",
                started_at=datetime.now(),
            )

            # Store the batch ID for this camera
            self._active_timelapse_batches[camera_name] = batch.id

            self.logger.info(
                f"Created timelapse batch {batch.id} for camera {camera_name}"
            )

        except Exception as e:
            self.logger.error(
                f"Failed to create timelapse batch for {camera_name}: {e}"
            )

    def _complete_timelapse_batch(self, camera_name: str) -> None:
        """Complete an active timelapse batch in the database"""
        try:
            if (
                not self._db_services
                or camera_name not in self._active_timelapse_batches
            ):
                return

            timelapse_service = self._db_services["timelapse_batch"]
            batch_id = self._active_timelapse_batches[camera_name]

            # Update batch status and completion time
            timelapse_service.update_batch_status(batch_id, status="completed")

            # Remove from active batches
            del self._active_timelapse_batches[camera_name]

            self.logger.info(
                f"Completed timelapse batch {batch_id} for camera {camera_name}"
            )

        except Exception as e:
            self.logger.error(
                f"Failed to complete timelapse batch for {camera_name}: {e}"
            )

    def get_enabled_cameras(self) -> List[CameraSettings]:
        """Get list of enabled camera configurations"""
        cameras = self.config.get_cameras_typed()
        return [camera for camera in cameras if camera.enabled]

    def get_camera_config(self, name: str) -> Optional[CameraSettings]:
        """Get camera configuration by name"""
        return self.config.get_camera_by_name_typed(name)

    def get_camera_state(self, name: str) -> Optional[CameraState]:
        """Get current camera state"""
        return self._camera_states.get(name)

    def get_all_camera_states(self) -> Dict[str, CameraState]:
        """
        Get states of all cameras.

        Returns:
            Dictionary mapping camera names to their states
        """
        return self._camera_states.copy()

    def is_camera_healthy(self, name: str, max_failures: int = 3) -> bool:
        """Check if camera is healthy (below max failure threshold)"""
        state = self.get_camera_state(name)
        if not state:
            return False
        return state.consecutive_failures < max_failures

    def update_camera_status(
        self, name: str, status: CameraStatus, error_message: Optional[str] = None
    ) -> None:
        """Update camera status and error information"""
        if name in self._camera_states:
            self._camera_states[name].status = status
            if error_message:
                self._camera_states[name].last_error = error_message

    def record_successful_capture(
        self,
        name: str,
        image_path: Optional[Path] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Record a successful capture for the camera"""
        if name in self._camera_states:
            state = self._camera_states[name]
            state.last_capture_time = datetime.now()
            state.consecutive_failures = 0
            state.total_captures += 1
            state.status = CameraStatus.ONLINE
            state.last_error = None

            if state.timelapse_state == TimelapseState.RUNNING:
                self.increment_timelapse_frame_count(name)

            # Log to database if services are available
            if self._db_services and image_path:
                self._log_capture_to_database(
                    name, True, image_path=image_path, duration_ms=duration_ms
                )

    def record_failed_capture(
        self, name: str, error_message: str, duration_ms: Optional[int] = None
    ) -> None:
        """Record a failed capture for the camera"""
        if name in self._camera_states:
            state = self._camera_states[name]
            state.consecutive_failures += 1
            state.last_error = error_message
            state.status = CameraStatus.ERROR

            # Log to database if services are available
            if self._db_services:
                self._log_capture_to_database(
                    name, False, error_message=error_message, duration_ms=duration_ms
                )

    async def capture_image_async(self, camera_name: str) -> Optional[Path]:
        """
        Capture image asynchronously for a single camera.

        Args:
            camera_name: Name of the camera

        Returns:
            Path to captured image or None if failed
        """
        camera_config = self.get_camera_config(camera_name)
        if not camera_config:
            self.logger.error(f"Camera '{camera_name}' not found in configuration")
            return None

        if not camera_config.enabled:
            self.logger.debug(f"Camera '{camera_name}' is disabled, skipping capture")
            return None

        start_time = time.perf_counter()
        duration_ms = None
        image_path = None

        try:
            # Run the blocking capture operation in a thread pool
            loop = asyncio.get_event_loop()
            image_path = await loop.run_in_executor(
                None, self._capture_image_sync, camera_name, camera_config
            )
            end_time = time.perf_counter()
            duration_ms = int((end_time - start_time) * 1000)

            if image_path:
                self.record_successful_capture(
                    camera_name, image_path, duration_ms=duration_ms
                )
                self.logger.debug(
                    f"Successfully captured image for '{camera_name}' in {duration_ms}ms: {image_path}"
                )
                return image_path
            else:
                # end_time might not be set if _capture_image_sync raised an exception before returning
                # but if it returned None, it means it completed (possibly with an internal error logged by _capture_image_sync)
                if duration_ms is None:  # Ensure duration_ms is set if not already
                    end_time = time.perf_counter()
                    duration_ms = int((end_time - start_time) * 1000)
                self.record_failed_capture(
                    camera_name, "Capture returned None", duration_ms=duration_ms
                )
                return None

        except Exception as e:
            end_time = time.perf_counter()
            duration_ms = int((end_time - start_time) * 1000)
            error_msg = f"Exception during capture: {e}"
            self.record_failed_capture(camera_name, error_msg, duration_ms=duration_ms)
            self.logger.exception(f"Failed to capture image for '{camera_name}'")
            return None

    def _capture_image_sync(
        self, camera_name: str, camera_config: CameraSettings
    ) -> Optional[Path]:
        """
        Synchronous image capture (to be run in thread pool).

        Args:
            camera_name: Name of the camera
            camera_config: Camera configuration object

        Returns:
            Path to captured image or None if failed
        """
        try:
            # Get storage directory and ensure it exists
            storage_path_str = self.config.get_storage_path()
            if not storage_path_str:
                raise ValueError(
                    f"Storage path not configured for camera '{camera_name}'"
                )

            # Use helper utility to create camera directories
            camera_storage_dir = file_management.ensure_camera_storage_exists(
                camera_name, self.config, self.logger
            )
            if not camera_storage_dir:
                raise ValueError(
                    f"Failed to create storage directory for camera '{camera_name}'"
                )

            # Extract camera settings
            camera_url = camera_config.url
            if not camera_url:
                raise ValueError(f"No URL configured for camera '{camera_name}'")

            # Get image settings from config
            image_settings = self.config.get_image_settings_typed()
            image_type = image_settings.image_type.value  # Convert enum to string
            # Get rotation from camera config
            rotation = (
                camera_config.rotation.value if camera_config.rotation else "none"
            )

            frames_dir = camera_storage_dir

            # Call the capture function with proper parameters
            return capture_image_from_camera(
                camera_name=camera_name,
                camera_url=camera_url,
                output_dir=frames_dir,
                image_type=image_type,
                rotate_option=rotation,
                logger=self.logger,
                # Pass image settings parameters
                retries=image_settings.image_capture_retries,
                retry_delay=image_settings.image_capture_sleep,
                image_width=image_settings.image_width,
                image_height=image_settings.image_height,
                timezone_str=self.config.get_timezone_str(),
                # Pass compression settings
                max_image_size=image_settings.max_image_size,
                compression_quality=image_settings.image_compression_quality,
            )

        except Exception as e:
            self.logger.error(f"Error in sync capture for '{camera_name}': {e}")
            return None

    async def capture_all_cameras(self) -> Dict[str, Optional[Path]]:
        """
        Capture images from all enabled cameras concurrently.
        Only captures from cameras with active timelapse states.

        Returns:
            Dictionary mapping camera names to captured image paths (or None for failures)
        """
        enabled_cameras = self.get_enabled_cameras()
        if not enabled_cameras:
            self.logger.warning("No enabled cameras found")
            return {}

        # Filter cameras to only those with active timelapse states
        active_cameras = [
            camera
            for camera in enabled_cameras
            if self.get_timelapse_state(camera.name) == TimelapseState.RUNNING
        ]

        if not active_cameras:
            self.logger.info("No cameras with active timelapse states found")
            return {}

        self.logger.info(
            f"Starting concurrent capture for {len(active_cameras)} cameras with active timelapse states"
        )

        # Check for shutdown signal before starting
        if self.shutdown_flag and self.shutdown_flag.is_set():
            self.logger.info("Shutdown requested, aborting capture")
            return {}

        # Create capture tasks for all active cameras
        capture_tasks = [
            asyncio.create_task(self.capture_image_async(camera.name))
            for camera in active_cameras
        ]

        # Create shutdown monitoring task
        shutdown_task = None
        if self.shutdown_flag:
            # Create a async task that checks the threading.Event
            async def check_shutdown():
                while self.shutdown_flag and not self.shutdown_flag.is_set():
                    await asyncio.sleep(0.1)

            shutdown_task = asyncio.create_task(check_shutdown())

        camera_names = [camera.name for camera in active_cameras]
        try:
            # Wait for either completion or shutdown signal
            tasks_to_wait = capture_tasks + ([shutdown_task] if shutdown_task else [])
            done, pending = await asyncio.wait(
                tasks_to_wait, return_when=asyncio.FIRST_COMPLETED
            )

            # If shutdown was triggered, cancel pending tasks
            if shutdown_task and shutdown_task in done:
                self.logger.info("Shutdown signal received, cancelling camera captures")
                for task in capture_tasks:
                    if not task.done():
                        task.cancel()
                # Wait briefly for cancellation to complete
                await asyncio.gather(*capture_tasks, return_exceptions=True)
                return {}

            # All capture tasks completed, cancel shutdown task
            if shutdown_task:
                shutdown_task.cancel()

            # Get results from completed capture tasks
            results = await asyncio.gather(*capture_tasks, return_exceptions=True)

        except asyncio.CancelledError:
            self.logger.info("Capture operation was cancelled")
            # Cancel all tasks
            tasks_to_cancel = capture_tasks + ([shutdown_task] if shutdown_task else [])
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
            return {}

        # Process results
        capture_results = {}
        for camera_name, result in zip(camera_names, results):
            if isinstance(result, Exception):
                self.logger.error(f"Capture task failed for '{camera_name}': {result}")
                capture_results[camera_name] = None
                self.record_failed_capture(camera_name, str(result))
            else:
                capture_results[camera_name] = result

        successful_captures = sum(
            1 for result in capture_results.values() if result is not None
        )
        self.logger.info(
            f"Capture cycle complete: {successful_captures}/{len(active_cameras)} successful"
        )

        # Increment frame count for successful captures
        for camera_name, result in capture_results.items():
            if result is not None:
                self.increment_timelapse_frame_count(camera_name)

        return capture_results

    def capture_all_cameras_sync(self) -> Dict[str, Optional[Path]]:
        """
        Synchronous version of capture_all_cameras for compatibility.
        Respects shutdown flag from main thread.

        Returns:
            Dictionary mapping camera names to captured image paths (or None for failures)
        """
        # Quick check for shutdown before doing any work
        if self.shutdown_flag and self.shutdown_flag.is_set():
            self.logger.info("Shutdown requested, skipping capture")
            return {}

        try:
            # Create a new event loop if none exists
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the async function with proper signal handling
            return loop.run_until_complete(self.capture_all_cameras())

        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received, stopping capture operations")
            if self.shutdown_flag:
                self.shutdown_flag.set()
            return {}
        except Exception as e:
            self.logger.error(f"Error in synchronous capture_all_cameras: {e}")
            return {}

    def get_camera_summary(self) -> Dict[str, Dict]:
        """
        Get summary of all camera states.

        Returns:
            Dictionary with camera states and statistics
        """
        return {
            name: {
                "status": state.status.value,
                "last_capture": (
                    state.last_capture_time.isoformat()
                    if state.last_capture_time
                    else None
                ),
                "total_captures": state.total_captures,
                "consecutive_failures": state.consecutive_failures,
                "last_error": state.last_error,
                "is_healthy": self.is_camera_healthy(name),
            }
            for name, state in self._camera_states.items()
        }

    def get_unhealthy_cameras(self) -> List[str]:
        """
        Get list of unhealthy camera names.

        Returns:
            List of camera names that are not healthy
        """
        return [
            name
            for name in self._camera_states.keys()
            if not self.is_camera_healthy(name)
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall camera statistics.

        Returns:
            Dictionary with aggregate statistics
        """
        total_cameras = len(self._camera_states)
        enabled_cameras = len(self.get_enabled_cameras())
        healthy_cameras = len(
            [
                name
                for name in self._camera_states.keys()
                if self.is_camera_healthy(name)
            ]
        )
        total_captures = sum(
            state.total_captures for state in self._camera_states.values()
        )

        return {
            "total_cameras": total_cameras,
            "enabled_cameras": enabled_cameras,
            "healthy_cameras": healthy_cameras,
            "unhealthy_cameras": total_cameras - healthy_cameras,
            "total_captures": total_captures,
            "capture_success_rate": self._calculate_success_rate(),
        }

    def _calculate_success_rate(self) -> float:
        """Calculate overall capture success rate"""
        total_attempts = sum(
            state.total_captures + state.consecutive_failures
            for state in self._camera_states.values()
        )
        if total_attempts == 0:
            return 0.0

        total_successes = sum(
            state.total_captures for state in self._camera_states.values()
        )
        return round((total_successes / total_attempts) * 100, 2)

    # ================================
    # TIMELAPSE CONTROL METHODS
    # ================================

    def start_timelapse(self, camera_name: str) -> bool:
        """
        Start timelapse recording for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            True if started successfully, False otherwise
        """
        if camera_name not in self._camera_states:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False

        state = self._camera_states[camera_name]

        if state.timelapse_state == TimelapseState.RUNNING:
            self.logger.warning(f"Timelapse already running for camera '{camera_name}'")
            return True

        state.timelapse_state = TimelapseState.RUNNING
        state.timelapse_started_at = datetime.now()
        state.timelapse_paused_at = None
        state.timelapse_frame_count = 0

        # Create timelapse batch in database if services are available
        if self._db_services:
            self._start_timelapse_batch(camera_name)

        self.logger.info(f"Started timelapse for camera '{camera_name}'")
        return True

    def pause_timelapse(self, camera_name: str) -> bool:
        """
        Pause timelapse recording for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            True if paused successfully, False otherwise
        """
        if camera_name not in self._camera_states:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False

        state = self._camera_states[camera_name]

        if state.timelapse_state != TimelapseState.RUNNING:
            self.logger.warning(
                f"Timelapse not running for camera '{camera_name}', cannot pause"
            )
            return False

        state.timelapse_state = TimelapseState.PAUSED
        state.timelapse_paused_at = datetime.now()

        self.logger.info(f"Paused timelapse for camera '{camera_name}'")
        return True

    def resume_timelapse(self, camera_name: str) -> bool:
        """
        Resume timelapse recording for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            True if resumed successfully, False otherwise
        """
        if camera_name not in self._camera_states:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False

        state = self._camera_states[camera_name]

        if state.timelapse_state != TimelapseState.PAUSED:
            self.logger.warning(
                f"Timelapse not paused for camera '{camera_name}', cannot resume"
            )
            return False

        state.timelapse_state = TimelapseState.RUNNING
        state.timelapse_paused_at = None

        self.logger.info(f"Resumed timelapse for camera '{camera_name}'")
        return True

    def stop_timelapse(self, camera_name: str) -> bool:
        """
        Stop timelapse recording for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            True if stopped successfully, False otherwise
        """
        if camera_name not in self._camera_states:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False

        state = self._camera_states[camera_name]

        if state.timelapse_state == TimelapseState.STOPPED:
            self.logger.warning(f"Timelapse already stopped for camera '{camera_name}'")
            return True

        state.timelapse_state = TimelapseState.STOPPED
        state.timelapse_paused_at = None

        # Complete timelapse batch in database if services are available
        if self._db_services:
            self._complete_timelapse_batch(camera_name)

        self.logger.info(f"Stopped timelapse for camera '{camera_name}'")
        return True

    def reset_timelapse(self, camera_name: str) -> bool:
        """
        Reset timelapse recording for a camera (clear frame count and times).

        Args:
            camera_name: Name of the camera

        Returns:
            True if reset successfully, False otherwise
        """
        if camera_name not in self._camera_states:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False

        state = self._camera_states[camera_name]

        # Reset timelapse state and counters
        state.timelapse_state = TimelapseState.STOPPED
        state.timelapse_frame_count = 0
        state.timelapse_started_at = None
        state.timelapse_paused_at = None

        # Clear captured frames for this camera
        try:
            storage_settings = self.config.get_storage_settings_typed()
            camera_frames_dir = (
                Path(storage_settings.output_dir) / camera_name / "frames"
            )

            if camera_frames_dir.exists():
                frames_cleared = 0
                for frame_file in camera_frames_dir.glob(f"{camera_name}_*"):
                    if frame_file.is_file():
                        frame_file.unlink()
                        frames_cleared += 1

                self.logger.info(
                    f"Cleared {frames_cleared} frames for camera '{camera_name}' during reset"
                )
            else:
                self.logger.debug(
                    f"No frames directory found for camera '{camera_name}'"
                )

        except Exception as e:
            self.logger.error(
                f"Error clearing frames for camera '{camera_name}' during reset: {e}"
            )

        self.logger.info(f"Reset timelapse for camera '{camera_name}'")
        return True

    def get_timelapse_state(self, camera_name: str) -> Optional[TimelapseState]:
        """
        Get the current timelapse state for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            Current timelapse state or None if camera not found
        """
        if camera_name not in self._camera_states:
            return None

        return self._camera_states[camera_name].timelapse_state

    def increment_timelapse_frame_count(self, camera_name: str) -> None:
        """
        Increment the timelapse frame count for a camera and update the database.
        """
        if camera_name in self._camera_states:
            state = self._camera_states[camera_name]
            state.timelapse_frame_count += 1
            self.logger.debug(
                f"Incremented in-memory frame count for {camera_name} to {state.timelapse_frame_count}"
            )

            if self._db_services and camera_name in self._active_timelapse_batches:
                try:
                    timelapse_service = self._db_services["timelapse_batch"]
                    batch_id = self._active_timelapse_batches[camera_name]
                    timelapse_service.update_batch_total_frames(
                        batch_id, state.timelapse_frame_count
                    )
                    self.logger.info(
                        f"Updated total_frames for batch {batch_id} to {state.timelapse_frame_count} in DB."
                    )
                except AttributeError:
                    self.logger.error(
                        f"TimelapseBatchService does not have 'update_batch_total_frames' method. DB not updated for batch {self._active_timelapse_batches.get(camera_name)}."
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to update total_frames in DB for batch {self._active_timelapse_batches.get(camera_name)}: {e}"
                    )
            elif (
                self._db_services and camera_name not in self._active_timelapse_batches
            ):
                self.logger.warning(
                    f"Cannot update frame count in DB: No active timelapse batch found for camera '{camera_name}'."
                )
            elif not self._db_services:
                self.logger.debug(
                    "DB services not available, skipping frame count update in DB."
                )
