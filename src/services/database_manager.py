#!/usr/bin/env python3
# src/services/database_manager.py
"""
Database Manager for UniFi Timelapser - Centralized database operations coordinator.
"""

import logging
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from core.config import Config
from core.models import CameraSettings
from database.database_services import (
    CameraService,
    ImageService,
    TimelapseBatchService,
    CaptureAttemptService,
    ShareService,
)
from database.models import Camera, Image, TimelapseBatch


class DatabaseManager:
    """
    Centralized database operations coordinator.

    Provides high-level database operations for the application,
    coordinating between different database services and handling
    transactions, migrations, and state synchronization.
    """

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize the Database Manager.

        Args:
            config: Application configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger

        # Initialize database services
        self.camera_service = CameraService()
        self.image_service = ImageService()
        self.batch_service = TimelapseBatchService()
        self.capture_service = CaptureAttemptService()
        self.sharing_service = ShareService()

        self._camera_cache: Dict[str, Camera] = {}
        self._camera_id_to_name: Dict[int, str] = {}

    def initialize_database(self) -> bool:
        """
        Initialize database schema and sync configurations.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self.logger.info("Initializing database...")

            # Sync cameras from config to database
            self._sync_cameras_from_config()

            self.logger.info("Database initialization completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            return False

    def _sync_cameras_from_config(self) -> None:
        """Synchronize camera configurations from config to database"""
        self.logger.info("Syncing camera configurations to database...")

        config_cameras = self.config.get_cameras_typed()

        for camera_config in config_cameras:
            try:
                # Generate URL hash for database storage
                url_hash = self._generate_url_hash(camera_config.url)

                # Check if camera already exists
                existing_camera = self.camera_service.get_camera_by_name(
                    camera_config.name
                )

                if existing_camera:
                    # Update existing camera
                    updated = self.camera_service.update_camera(
                        existing_camera.id,  # type: ignore
                        url_hash=url_hash,
                        enabled=camera_config.enabled,
                        rotation=(
                            camera_config.rotation.value
                            if camera_config.rotation
                            else "none"
                        ),
                        camera_metadata=self._build_camera_metadata(camera_config),
                    )
                    if updated:
                        self.logger.debug(
                            f"Updated camera configuration for '{camera_config.name}'"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to update camera '{camera_config.name}'"
                        )
                else:
                    # Create new camera
                    new_camera = self.camera_service.create_camera(
                        name=camera_config.name,
                        url_hash=url_hash,
                        enabled=camera_config.enabled,
                        rotation=(
                            camera_config.rotation.value
                            if camera_config.rotation
                            else "none"
                        ),
                        camera_metadata=self._build_camera_metadata(camera_config),
                    )
                    self.logger.info(
                        f"Created new camera '{camera_config.name}' in database"
                    )

            except Exception as e:
                self.logger.error(f"Failed to sync camera '{camera_config.name}': {e}")

        # Update cache
        self._refresh_camera_cache()

    def _generate_url_hash(self, url: str) -> str:
        """Generate a hash for the camera URL for database storage"""
        return hashlib.sha256(url.encode()).hexdigest()[:32]

    def _build_camera_metadata(self, camera_config: CameraSettings) -> Dict[str, Any]:
        """Build metadata dictionary from camera configuration"""
        return {
            "url": camera_config.url,
            "original_config": {
                "rotation": (
                    camera_config.rotation.value if camera_config.rotation else "none"
                ),
                "enabled": camera_config.enabled,
            },
        }

    def _refresh_camera_cache(self) -> None:
        """Refresh the internal camera cache"""
        try:
            cameras = self.camera_service.get_all_cameras()
            self._camera_cache = {camera.name: camera for camera in cameras}  # type: ignore
            self._camera_id_to_name = {camera.id: camera.name for camera in cameras}  # type: ignore
            self.logger.debug(f"Refreshed camera cache with {len(cameras)} cameras")
        except Exception as e:
            self.logger.error(f"Failed to refresh camera cache: {e}")

    def get_camera_by_name(self, name: str) -> Optional[Camera]:
        """Get camera from cache or database"""
        if name in self._camera_cache:
            return self._camera_cache[name]

        camera = self.camera_service.get_camera_by_name(name)
        if camera:
            self._camera_cache[name] = camera
            self._camera_id_to_name[camera.id] = name  # type: ignore
        return camera

    def record_successful_capture(
        self, camera_name: str, image_path: Path, **kwargs
    ) -> Optional[Image]:
        """
        Record a successful image capture in the database.

        Args:
            camera_name: Name of the camera
            image_path: Path to the captured image
            **kwargs: Additional metadata for the image

        Returns:
            Created Image record or None if failed
        """
        try:
            camera = self.get_camera_by_name(camera_name)
            if not camera:
                self.logger.error(f"Camera '{camera_name}' not found in database")
                return None

            # Get image metadata
            file_stats = image_path.stat()

            # Create image record
            image = self.image_service.create_image(
                camera_id=camera.id,  # type: ignore
                filename=image_path.name,
                file_path=str(image_path),
                file_size_bytes=file_stats.st_size,
                format=image_path.suffix.upper().lstrip("."),
                captured_at=datetime.fromtimestamp(file_stats.st_mtime),
                **kwargs,
            )

            # Update camera health
            self.camera_service.update_health_check(camera.id, True)  # type: ignore

            self.logger.debug(
                f"Recorded successful capture for '{camera_name}': {image_path.name}"
            )
            return image

        except Exception as e:
            self.logger.error(f"Failed to record capture for '{camera_name}': {e}")
            return None

    def record_failed_capture(self, camera_name: str, error_message: str) -> bool:
        """
        Record a failed capture attempt.

        Args:
            camera_name: Name of the camera
            error_message: Error message describing the failure

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            camera = self.get_camera_by_name(camera_name)
            if not camera:
                self.logger.error(f"Camera '{camera_name}' not found in database")
                return False

            # Record capture attempt
            self.capture_service.create_attempt(
                camera_id=camera.id,  # type: ignore
                status="failed",
                error_message=error_message,
            )

            # Update camera health
            self.camera_service.update_health_check(camera.id, False)  # type: ignore

            self.logger.debug(
                f"Recorded failed capture for '{camera_name}': {error_message}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to record capture failure for '{camera_name}': {e}"
            )
            return False

    def create_timelapse_batch(
        self,
        camera_name: str,
        batch_type: str,
        generation_mode: str = "manual_only",
        frame_rate: int = 30,
        **kwargs,
    ) -> Optional[TimelapseBatch]:
        """
        Create a new timelapse batch.

        Args:
            camera_name: Name of the camera
            batch_type: Type of batch (manual, checkpoint, rolling)
            generation_mode: Generation mode
            frame_rate: Frame rate for the timelapse
            **kwargs: Additional batch parameters

        Returns:
            Created TimelapseBatch record or None if failed
        """
        try:
            camera = self.get_camera_by_name(camera_name)
            if not camera:
                self.logger.error(f"Camera '{camera_name}' not found in database")
                return None

            batch = self.batch_service.create_batch(
                camera_id=camera.id,  # type: ignore
                batch_type=batch_type,
                generation_mode=generation_mode,
                frame_rate=frame_rate,
                **kwargs,
            )

            self.logger.info(
                f"Created timelapse batch for '{camera_name}': {batch_type} (ID: {batch.id})"
            )
            return batch

        except Exception as e:
            self.logger.error(
                f"Failed to create timelapse batch for '{camera_name}': {e}"
            )
            return None

    def update_timelapse_batch_status(
        self,
        batch_id: int,
        status: str,
        output_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update timelapse batch status.

        Args:
            batch_id: ID of the batch
            status: New status (pending, processing, completed, failed)
            output_path: Path to generated timelapse video
            error_message: Error message if failed

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            update_data = {"status": status}

            if output_path:
                update_data["output_path"] = output_path
            if error_message:
                update_data["error_message"] = error_message

            updated = self.batch_service.update_batch_status(
                batch_id, status, error_message
            )

            if updated:
                self.logger.debug(f"Updated batch {batch_id} status to '{status}'")
            else:
                self.logger.warning(f"Failed to update batch {batch_id}")

            return updated

        except Exception as e:
            self.logger.error(f"Failed to update batch {batch_id}: {e}")
            return False

    def get_images_for_timelapse(
        self,
        camera_name: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> List[Image]:
        """
        Get images for creating a timelapse.

        Args:
            camera_name: Name of the camera
            start_date: Start date for image selection
            end_date: End date for image selection
            limit: Maximum number of images to return

        Returns:
            List of Image records
        """
        try:
            camera = self.get_camera_by_name(camera_name)
            if not camera:
                self.logger.error(f"Camera '{camera_name}' not found in database")
                return []

            # Use date range method if dates provided, otherwise use basic method
            if start_date and end_date:
                # Convert dates to datetime if needed
                if isinstance(start_date, date) and not isinstance(
                    start_date, datetime
                ):
                    start_datetime = datetime.combine(start_date, datetime.min.time())
                else:
                    start_datetime = start_date

                if isinstance(end_date, date) and not isinstance(end_date, datetime):
                    end_datetime = datetime.combine(end_date, datetime.max.time())
                else:
                    end_datetime = end_date

                images = self.image_service.get_images_by_date_range(
                    camera.id, start_datetime, end_datetime  # type: ignore
                )
                if limit:
                    images = images[:limit]
            else:
                images = self.image_service.get_images_by_camera(
                    camera.id, limit=limit  # type: ignore
                )

            self.logger.debug(
                f"Retrieved {len(images)} images for '{camera_name}' timelapse"
            )
            return images

        except Exception as e:
            self.logger.error(f"Failed to get images for '{camera_name}': {e}")
            return []

    def get_camera_statistics(self, camera_name: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a camera.

        Args:
            camera_name: Name of the camera

        Returns:
            Dictionary with camera statistics
        """
        try:
            camera = self.get_camera_by_name(camera_name)
            if not camera:
                return {}

            # Get image count
            images = self.image_service.get_images_by_camera(camera.id)  # type: ignore
            image_count = len(images)

            # Get recent images (last 24 hours)
            yesterday = datetime.now() - timedelta(days=1)
            today = datetime.now()
            recent_images = self.image_service.get_images_by_date_range(
                camera.id, yesterday, today  # type: ignore
            )

            # Get timelapse batches
            batches = self.batch_service.get_batches_by_camera(camera.id)  # type: ignore

            return {
                "camera_id": camera.id,
                "camera_name": camera_name,
                "enabled": camera.enabled,
                "total_images": image_count,
                "recent_images_24h": len(recent_images),
                "total_batches": len(batches),
                "last_health_check": camera.last_health_check,
                "connection_failures": camera.connection_failures,
                "created_at": camera.created_at,
                "updated_at": camera.updated_at,
            }

        except Exception as e:
            self.logger.error(f"Failed to get statistics for '{camera_name}': {e}")
            return {}

    def cleanup_old_data(self, days_to_keep: int = 30) -> Dict[str, int]:
        """
        Clean up old database records.

        Args:
            days_to_keep: Number of days of data to keep

        Returns:
            Dictionary with cleanup statistics
        """
        try:
            cutoff_date = datetime.now().date()
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_to_keep)

            stats = {
                "images_deleted": 0,
                "batches_deleted": 0,
                "capture_attempts_deleted": 0,
            }

            # TODO: Clean up old images. rightn ow it just logs
            self.logger.info(
                f"Database cleanup requested for data older than {days_to_keep} days"
            )

            return stats

        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
            return {}

    @contextmanager
    def transaction(self):
        """Context manager for database transactions"""
        # TODO: Needs implemented with good transaction management. Right now it just provide a simple context
        try:
            yield self
        except Exception as e:
            self.logger.error(f"Transaction failed: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        """
        Perform database health check.

        Returns:
            Dictionary with health check results
        """
        try:
            # Test basic database connectivity
            cameras = self.camera_service.get_all_cameras()

            return {
                "database_connected": True,
                "total_cameras": len(cameras),
                "services_available": [
                    "camera_service",
                    "image_service",
                    "batch_service",
                    "capture_service",
                    "sharing_service",
                ],
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "database_connected": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
