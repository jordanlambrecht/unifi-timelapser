#!/usr/bin/env python3
# src/database/database_services.py
"""
Database services for UniFi Timelapser.
Provides CRUD operations that work correctly with SQLAlchemy models.
"""

import os
import hashlib
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Union, Tuple
from pathlib import Path
from sqlalchemy import and_, desc, func, update
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

try:
    from database.connection import get_database_manager
except ImportError:
    from .connection import get_database_manager

try:
    from database.models import (
        Camera,
        Image,
        TimelapseBatch,
        TimelapseImage,
        CaptureAttempt,
        Share,
        ShareBatch,
        ShareCustomization,
    )
except ImportError:
    from .models import (
        Camera,
        Image,
        TimelapseBatch,
        TimelapseImage,
        CaptureAttempt,
        Share,
        ShareBatch,
        ShareCustomization,
    )


class DatabaseService:
    """Base database service with common functionality"""

    def __init__(self):
        self._db_manager = None

    @property
    def db_manager(self):
        """Lazy loading of database manager"""
        if self._db_manager is None:
            self._db_manager = get_database_manager()
        return self._db_manager

    def get_session(self):
        """Get a database session"""
        return self.db_manager.get_session()


class CameraService(DatabaseService):
    """Service for camera-related database operations"""

    def create_camera(self, name: str, url_hash: str, **kwargs) -> Camera:
        """Create a new camera"""
        with self.get_session() as session:
            camera = Camera(name=name, url_hash=url_hash, **kwargs)
            session.add(camera)
            session.commit()
            session.refresh(camera)
            # Expunge the object from session so it can be used after session closes
            session.expunge(camera)
            return camera

    def get_camera_by_id(self, camera_id: int) -> Optional[Camera]:
        """Get camera by ID"""
        with self.get_session() as session:
            camera = session.query(Camera).filter(Camera.id == camera_id).first()
            if camera:
                session.expunge(camera)
            return camera

    def get_camera_by_name(self, name: str) -> Optional[Camera]:
        """Get camera by name"""
        with self.get_session() as session:
            camera = session.query(Camera).filter(Camera.name == name).first()
            if camera:
                session.expunge(camera)
            return camera

    def get_all_cameras(self, enabled_only: bool = False) -> List[Camera]:
        """Get all cameras, optionally filtered by enabled status"""
        with self.get_session() as session:
            query = session.query(Camera)
            if enabled_only:
                query = query.filter(Camera.enabled == True)
            cameras = query.order_by(Camera.name).all()
            # Expunge all cameras from session so they can be used after session closes
            for camera in cameras:
                session.expunge(camera)
            return cameras

    def update_camera(self, camera_id: int, **kwargs) -> bool:
        """Update camera properties"""
        with self.get_session() as session:
            result = session.execute(
                update(Camera).where(Camera.id == camera_id).values(**kwargs)
            )
            session.commit()
            return result.rowcount > 0

    def update_health_check(self, camera_id: int, success: bool) -> bool:
        """Update camera health check status"""
        with self.get_session() as session:
            values = {
                "last_health_check": datetime.utcnow(),
                "connection_failures": 0 if success else Camera.connection_failures + 1,
            }
            session.execute(
                update(Camera).where(Camera.id == camera_id).values(**values)
            )
            session.commit()
            return True

    def delete_camera(self, camera_id: int) -> bool:
        """Delete a camera and all associated data"""
        with self.get_session() as session:
            camera = session.query(Camera).filter(Camera.id == camera_id).first()
            if camera:
                session.delete(camera)
                session.commit()
                return True
            return False

    def calculate_day_number(
        self, camera_id: int, capture_time: datetime
    ) -> Optional[int]:
        """Calculate day number for a camera based on its start date"""
        camera = self.get_camera_by_id(camera_id)
        # Check that camera exists and has day counter configuration
        if (
            camera
            and getattr(camera, "day_counter_enabled", False)
            and getattr(camera, "day_counter_start_date", None) is not None
        ):
            capture_date = capture_time.date()
            delta = capture_date - camera.day_counter_start_date
            return delta.days + 1 if delta.days >= 0 else None
        return None


class ImageService(DatabaseService):
    """Service for image-related database operations"""

    def create_image(
        self,
        camera_id: int,
        filename: str,
        file_path: str,
        file_size_bytes: int,
        format: str,
        captured_at: datetime,
        **kwargs,
    ) -> Image:
        """Create a new image record"""
        with self.get_session() as session:
            # Calculate day number if camera has day counter enabled
            camera_service = CameraService()
            day_number = camera_service.calculate_day_number(camera_id, captured_at)

            image = Image(
                camera_id=camera_id,
                filename=filename,
                file_path=file_path,
                file_size_bytes=file_size_bytes,
                format=format,
                captured_at=captured_at,
                day_number=day_number,
                **kwargs,
            )
            session.add(image)
            session.commit()
            session.refresh(image)
            session.expunge(image)
            return image

    def get_image_by_id(self, image_id: int) -> Optional[Image]:
        """Get image by ID"""
        with self.get_session() as session:
            image = session.query(Image).filter(Image.id == image_id).first()
            if image:
                session.expunge(image)
            return image

    def get_images_by_camera(
        self,
        camera_id: int,
        limit: Optional[int] = None,
        offset: int = 0,
        order_desc: bool = True,
    ) -> List[Image]:
        """Get images for a camera with pagination"""
        with self.get_session() as session:
            query = session.query(Image).filter(Image.camera_id == camera_id)

            if order_desc:
                query = query.order_by(desc(Image.captured_at))
            else:
                query = query.order_by(Image.captured_at)

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            images = query.all()
            for image in images:
                session.expunge(image)
            return images

    def get_images_by_date_range(
        self, camera_id: int, start_date: datetime, end_date: datetime
    ) -> List[Image]:
        """Get images within a date range"""
        with self.get_session() as session:
            return (
                session.query(Image)
                .filter(
                    and_(
                        Image.camera_id == camera_id,
                        Image.captured_at >= start_date,
                        Image.captured_at <= end_date,
                    )
                )
                .order_by(Image.captured_at)
                .all()
            )

    def get_latest_image(self, camera_id: int) -> Optional[Image]:
        """Get the most recent image for a camera"""
        with self.get_session() as session:
            return (
                session.query(Image)
                .filter(Image.camera_id == camera_id)
                .order_by(desc(Image.captured_at))
                .first()
            )

    def count_images_by_camera(self, camera_id: int) -> int:
        """Count total images for a camera"""
        with self.get_session() as session:
            return session.query(Image).filter(Image.camera_id == camera_id).count()

    def update_image_metadata(self, image_id: int, metadata: Dict[str, Any]) -> bool:
        """Update image processing metadata"""
        with self.get_session() as session:
            image = session.query(Image).filter(Image.id == image_id).first()
            if image:
                # Safely handle JSONB update - access the actual attribute value
                current_metadata = getattr(image, "processing_metadata", None)
                if not current_metadata or not isinstance(current_metadata, dict):
                    current_metadata = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                updated_metadata = {**current_metadata, **metadata}
                session.execute(
                    update(Image)
                    .where(Image.id == image_id)
                    .values(processing_metadata=updated_metadata)
                )
                session.commit()
                return True
            return False

    def delete_image(self, image_id: int) -> bool:
        """Delete an image record"""
        with self.get_session() as session:
            image = session.query(Image).filter(Image.id == image_id).first()
            if image:
                session.delete(image)
                session.commit()
                return True
            return False


class TimelapseBatchService(DatabaseService):
    """Service for timelapse batch operations"""

    def create_batch(
        self, camera_id: int, batch_type: str, generation_mode: str, **kwargs
    ) -> TimelapseBatch:
        """Create a new timelapse batch"""
        with self.get_session() as session:
            batch = TimelapseBatch(
                camera_id=camera_id,
                batch_type=batch_type,
                generation_mode=generation_mode,
                **kwargs,
            )
            session.add(batch)
            session.commit()
            session.refresh(batch)
            session.expunge(batch)
            return batch

    def get_batch_by_id(self, batch_id: int) -> Optional[TimelapseBatch]:
        """Get batch by ID with related data"""
        with self.get_session() as session:
            batch = (
                session.query(TimelapseBatch)
                .options(
                    joinedload(TimelapseBatch.camera),
                    selectinload(TimelapseBatch.timelapse_images).joinedload(
                        TimelapseImage.image
                    ),
                )
                .filter(TimelapseBatch.id == batch_id)
                .first()
            )
            if batch:
                session.expunge(batch)
            return batch

    def get_batches_by_camera(
        self, camera_id: int, status: Optional[str] = None, limit: Optional[int] = None
    ) -> List[TimelapseBatch]:
        """Get batches for a camera"""
        with self.get_session() as session:
            query = session.query(TimelapseBatch).filter(
                TimelapseBatch.camera_id == camera_id
            )

            if status:
                query = query.filter(TimelapseBatch.status == status)

            query = query.order_by(desc(TimelapseBatch.created_at))

            if limit:
                query = query.limit(limit)

            return query.all()

    def get_pending_batches(self) -> List[TimelapseBatch]:
        """Get all pending batches for processing"""
        with self.get_session() as session:
            return (
                session.query(TimelapseBatch)
                .filter(TimelapseBatch.status == "pending")
                .order_by(TimelapseBatch.created_at)
                .all()
            )

    def update_batch_status(
        self, batch_id: int, status: str, error_message: Optional[str] = None
    ) -> bool:
        """Update batch status"""
        with self.get_session() as session:
            values: Dict[str, Any] = {"status": status}

            if status == "processing":
                values["started_at"] = datetime.utcnow()
            elif status in ["completed", "failed"]:
                values["completed_at"] = datetime.utcnow()

            if error_message:
                values["error_message"] = error_message

            session.execute(
                update(TimelapseBatch)
                .where(TimelapseBatch.id == batch_id)
                .values(**values)
            )
            session.commit()
            # Return True if a row was updated, False otherwise
            # result.rowcount might not be available or reliable for all DBs/drivers after an update
            return True

    def update_batch_total_frames(self, batch_id: int, total_frames: int) -> bool:
        """Update the total_frames count for a specific timelapse batch."""
        with self.get_session() as session:
            try:
                result = session.execute(
                    update(TimelapseBatch)
                    .where(TimelapseBatch.id == batch_id)
                    .values(total_frames=total_frames)
                )
                session.commit()
                return result.rowcount > 0  # Check if any row was actually updated
            except SQLAlchemyError as e:
                print(f"Error updating total_frames for batch {batch_id}: {e}")
                session.rollback()
                return False

    def update_batch_output(
        self,
        batch_id: int,
        output_filename: str,
        output_path: str,
        file_size_bytes: int,
        duration_seconds: Optional[float] = None,
    ) -> bool:
        """Update batch output information"""
        with self.get_session() as session:
            values = {
                "output_filename": output_filename,
                "output_path": output_path,
                "file_size_bytes": file_size_bytes,
            }
            if duration_seconds:
                values["duration_seconds"] = duration_seconds

            session.execute(
                update(TimelapseBatch)
                .where(TimelapseBatch.id == batch_id)
                .values(**values)
            )
            session.commit()
            return True

    def add_images_to_batch(self, batch_id: int, image_ids: List[int]) -> bool:
        """Add images to a timelapse batch"""
        with self.get_session() as session:
            # Get current max sequence order
            max_order = (
                session.query(func.max(TimelapseImage.sequence_order))
                .filter(TimelapseImage.timelapse_batch_id == batch_id)
                .scalar()
                or 0
            )

            # Add images with sequential order
            for i, image_id in enumerate(image_ids):
                timelapse_image = TimelapseImage(
                    timelapse_batch_id=batch_id,
                    image_id=image_id,
                    sequence_order=max_order + i + 1,
                )
                session.add(timelapse_image)

            # Update total frames count
            total_frames = session.query(TimelapseImage).filter(
                TimelapseImage.timelapse_batch_id == batch_id
            ).count() + len(image_ids)

            session.execute(
                update(TimelapseBatch)
                .where(TimelapseBatch.id == batch_id)
                .values(total_frames=total_frames)
            )

            session.commit()
            return True

    def get_batch_images(self, batch_id: int) -> List[Image]:
        """Get all images in a batch in sequence order"""
        with self.get_session() as session:
            return (
                session.query(Image)
                .join(TimelapseImage)
                .filter(TimelapseImage.timelapse_batch_id == batch_id)
                .order_by(TimelapseImage.sequence_order)
                .all()
            )

    def get_active_batches(self) -> List[TimelapseBatch]:
        """Get all active (processing) batches"""
        with self.get_session() as session:
            batches = (
                session.query(TimelapseBatch)
                .filter(TimelapseBatch.status == "processing")
                .order_by(TimelapseBatch.created_at)
                .all()
            )
            # Expunge all batches to avoid session issues
            for batch in batches:
                session.expunge(batch)
            return batches

    def cleanup_stale_processing_batches(
        self, camera_id: int, batch_type: str = "continuous"
    ) -> int:
        """Clean up stale processing batches for a camera, keeping only the most recent one active.

        Returns:
            int: Number of batches that were marked as completed
        """
        with self.get_session() as session:
            # Get all processing batches for this camera and batch type, ordered by creation time (newest first)
            processing_batches = (
                session.query(TimelapseBatch)
                .filter(
                    TimelapseBatch.camera_id == camera_id,
                    TimelapseBatch.batch_type == batch_type,
                    TimelapseBatch.status == "processing",
                )
                .order_by(desc(TimelapseBatch.created_at))
                .all()
            )

            if len(processing_batches) <= 1:
                return 0  # Nothing to clean up

            # Keep the most recent batch active, mark the rest as completed
            batches_to_complete = processing_batches[
                1:
            ]  # Skip the first (most recent) one
            completed_count = 0

            for batch in batches_to_complete:
                # Update the batch using SQLAlchemy update
                session.execute(
                    update(TimelapseBatch)
                    .where(TimelapseBatch.id == batch.id)
                    .values(
                        status="completed",
                        completed_at=datetime.utcnow(),
                        error_message="Auto-completed due to application restart",
                    )
                )
                completed_count += 1

            session.commit()
            return completed_count

    def get_processing_batches_by_camera(
        self, camera_id: int, batch_type: str = "continuous"
    ) -> List[TimelapseBatch]:
        """Get all processing batches for a specific camera and batch type"""
        with self.get_session() as session:
            batches = (
                session.query(TimelapseBatch)
                .filter(
                    TimelapseBatch.camera_id == camera_id,
                    TimelapseBatch.batch_type == batch_type,
                    TimelapseBatch.status == "processing",
                )
                .order_by(desc(TimelapseBatch.created_at))
                .all()
            )
            # Expunge all batches to avoid session issues
            for batch in batches:
                session.expunge(batch)
            return batches

    def get_most_recent_processing_batch(
        self, camera_id: int, batch_type: str = "continuous"
    ) -> Optional[TimelapseBatch]:
        """Get the most recent processing batch for a camera and batch type"""
        with self.get_session() as session:
            batch = (
                session.query(TimelapseBatch)
                .filter(
                    TimelapseBatch.camera_id == camera_id,
                    TimelapseBatch.batch_type == batch_type,
                    TimelapseBatch.status == "processing",
                )
                .order_by(desc(TimelapseBatch.created_at))
                .first()
            )
            if batch:
                session.expunge(batch)
            return batch


class CaptureAttemptService(DatabaseService):
    """Service for capture attempt tracking"""

    def create_attempt(
        self,
        camera_id: int,
        status: str,
        image_id: Optional[int] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        retry_count: int = 0,
    ) -> CaptureAttempt:
        """Create a new capture attempt record"""
        with self.get_session() as session:
            attempt = CaptureAttempt(
                camera_id=camera_id,
                status=status,
                image_id=image_id,
                error_message=error_message,
                duration_ms=duration_ms,
                retry_count=retry_count,
            )
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
            return attempt

    def get_recent_attempts(
        self, camera_id: int, hours: int = 24
    ) -> List[CaptureAttempt]:
        """Get recent capture attempts for a camera"""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.get_session() as session:
            return (
                session.query(CaptureAttempt)
                .filter(
                    and_(
                        CaptureAttempt.camera_id == camera_id,
                        CaptureAttempt.attempted_at >= since,
                    )
                )
                .order_by(desc(CaptureAttempt.attempted_at))
                .all()
            )

    def get_success_rate(self, camera_id: int, hours: int = 24) -> float:
        """Calculate capture success rate for a camera"""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.get_session() as session:
            total = (
                session.query(CaptureAttempt)
                .filter(
                    and_(
                        CaptureAttempt.camera_id == camera_id,
                        CaptureAttempt.attempted_at >= since,
                    )
                )
                .count()
            )

            if total == 0:
                return 1.0

            successful = (
                session.query(CaptureAttempt)
                .filter(
                    and_(
                        CaptureAttempt.camera_id == camera_id,
                        CaptureAttempt.attempted_at >= since,
                        CaptureAttempt.status == "success",
                    )
                )
                .count()
            )

            return successful / total


class ShareService(DatabaseService):
    """Service for sharing system operations"""

    def create_share(
        self, title: str, share_type: str, timelapse_batch_ids: List[int], **kwargs
    ) -> Share:
        """Create a new share with associated batches"""
        with self.get_session() as session:
            share = Share(title=title, share_type=share_type, **kwargs)
            session.add(share)
            session.flush()  # Get the share ID

            # Add timelapse batches
            for i, batch_id in enumerate(timelapse_batch_ids):
                share_batch = ShareBatch(
                    share_id=share.id, timelapse_batch_id=batch_id, display_order=i + 1
                )
                session.add(share_batch)

            # Create default customization
            customization = ShareCustomization(share_id=share.id)
            session.add(customization)

            session.commit()
            session.refresh(share)
            return share

    def get_share_by_token(self, share_token: Union[str, uuid.UUID]) -> Optional[Share]:
        """Get share by token"""
        if isinstance(share_token, str):
            share_token = uuid.UUID(share_token)

        with self.get_session() as session:
            return (
                session.query(Share)
                .options(
                    selectinload(Share.share_batches).joinedload(
                        ShareBatch.timelapse_batch
                    ),
                    joinedload(Share.share_customization),
                )
                .filter(Share.share_token == share_token)
                .first()
            )

    def increment_view_count(self, share_token: Union[str, uuid.UUID]) -> bool:
        """Increment share view count"""
        if isinstance(share_token, str):
            share_token = uuid.UUID(share_token)

        with self.get_session() as session:
            session.execute(
                update(Share)
                .where(Share.share_token == share_token)
                .values(view_count=Share.view_count + 1)
            )
            session.commit()
            return True


# Initialize service instances
camera_service = CameraService()
image_service = ImageService()
timelapse_batch_service = TimelapseBatchService()
capture_attempt_service = CaptureAttemptService()
share_service = ShareService()
