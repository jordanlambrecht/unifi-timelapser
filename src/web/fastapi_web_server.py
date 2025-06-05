#!/usr/bin/env python3
# src/web/fastapi_web_server.py
"""
FastAPI web server for UniFi Timelapser camera monitoring dashboard and API.
Provides both a REST API and a web interface for monitoring camera health and status.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.config import Config
from core.models import CameraStatus, CameraState
from services.camera_manager import CameraManager
from services.timelapse_service import TimelapseService
from utils.common import get_time_ago, calculate_next_capture_time


# Pydantic models for API responses
class HealthStatusResponse(BaseModel):
    status: str
    data: Dict[str, Any]


class CameraListResponse(BaseModel):
    status: str
    data: List[Dict[str, Any]]
    count: int
    timestamp: str


class CameraDetailResponse(BaseModel):
    status: str
    data: Dict[str, Any]
    timestamp: str


class SystemStatsResponse(BaseModel):
    status: str
    data: Dict[str, Any]
    timestamp: str


class ImageListResponse(BaseModel):
    status: str
    data: List[Dict[str, Any]]
    count: int
    camera: str
    timestamp: str


class ManualTimelapseResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str


class TimelapseControlResponse(BaseModel):
    status: str
    message: str
    camera_name: str
    timelapse_state: str
    timestamp: str


class UniFiTimelapserAPI:
    """
    REST API endpoints for UniFi Timelapser.
    Provides programmatic access to camera status and system health.
    """

    def __init__(
        self,
        camera_manager: CameraManager,
        config: Config,
        logger: logging.Logger,
        timelapse_service: TimelapseService,
    ):
        """Initialize API with dependencies."""
        self.camera_manager = camera_manager
        self.config = config
        self.logger = logger
        self.timelapse_service = timelapse_service

    async def get_health_status(self) -> HealthStatusResponse:
        """System health check endpoint."""
        try:
            cameras = self._get_camera_status_data()
            total_cameras = len(cameras)
            online_cameras = len([c for c in cameras if c["status"] == "online"])
            error_cameras = len([c for c in cameras if c["status"] == "error"])

            health_status = "healthy"
            if error_cameras > 0:
                health_status = "degraded" if online_cameras > 0 else "critical"
            elif online_cameras == 0 and total_cameras > 0:
                health_status = "offline"

            return HealthStatusResponse(
                status="success",
                data={
                    "health_status": health_status,
                    "total_cameras": total_cameras,
                    "online_cameras": online_cameras,
                    "error_cameras": error_cameras,
                    "healthy_cameras": len(
                        [c for c in cameras if c.get("is_healthy", False)]
                    ),
                    "uptime_seconds": self._get_uptime_seconds(),
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(f"Error in health endpoint: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_cameras_list(self) -> CameraListResponse:
        """Get list of all cameras with status."""
        try:
            cameras = self._get_camera_status_data()
            return CameraListResponse(
                status="success",
                data=cameras,
                count=len(cameras),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            self.logger.error(f"Error getting cameras list: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_camera_detail(self, camera_name: str) -> CameraDetailResponse:
        """Get detailed information for a specific camera."""
        try:
            camera_state = self.camera_manager.get_camera_state(camera_name)
            camera_config = self.camera_manager.get_camera_config(camera_name)

            if not camera_state or not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            camera_data = self._camera_state_to_dict(camera_state)
            camera_data.update(
                {
                    "url": camera_config.url,
                    "enabled": camera_config.enabled,
                    "rotation": camera_config.rotation.value,
                    "latest_image": self._get_latest_image_info(camera_name),
                    "capture_history": self._get_capture_history(camera_name),
                    "storage_info": self._get_camera_storage_info(camera_name),
                    "latest_timelapse": self._get_latest_timelapse_info(camera_name),
                }
            )

            return CameraDetailResponse(
                status="success", data=camera_data, timestamp=datetime.now().isoformat()
            )
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error getting camera {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_camera_images(
        self, camera_name: str, limit: int = 10
    ) -> ImageListResponse:
        """Get list of recent images for a camera."""
        try:
            images = self._get_camera_images(camera_name, limit)

            return ImageListResponse(
                status="success",
                data=images,
                count=len(images),
                camera=camera_name,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            self.logger.error(f"Error getting images for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_system_stats(self) -> SystemStatsResponse:
        """Get comprehensive system statistics."""
        try:
            stats = self.camera_manager.get_statistics()
            storage_stats = self._get_storage_statistics()

            return SystemStatsResponse(
                status="success",
                data={
                    "cameras": stats,
                    "storage": storage_stats,
                    "system": {
                        "uptime_seconds": self._get_uptime_seconds(),
                        "config_valid": self.config.is_config_valid(),
                        "capture_interval": self.config.get_capture_interval(),
                        "timezone": self.config.get_timezone_str(),
                    },
                },
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            self.logger.error(f"Error getting system stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def generate_manual_timelapse(
        self, camera_name: str, checkpoint: bool = False
    ) -> ManualTimelapseResponse:
        """Generate a manual timelapse for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            self.logger.info(
                f"Starting manual timelapse generation for camera: {camera_name}"
            )

            # Generate the timelapse using the timelapse service
            result_path = self.timelapse_service.create_timelapse(
                camera_name, checkpoint=checkpoint
            )

            if result_path:
                # Get file size and other info about the generated timelapse
                file_size_mb = result_path.stat().st_size / (1024 * 1024)

                return ManualTimelapseResponse(
                    status="success",
                    message=f"Timelapse generated successfully for camera {camera_name}",
                    data={
                        "camera_name": camera_name,
                        "output_path": str(result_path),
                        "file_size_mb": round(file_size_mb, 2),
                        "checkpoint": checkpoint,
                        "timelapse_type": "checkpoint" if checkpoint else "manual",
                    },
                    timestamp=datetime.now().isoformat(),
                )
            else:
                return ManualTimelapseResponse(
                    status="error",
                    message=f"Failed to generate timelapse for camera {camera_name}. Check logs for details.",
                    timestamp=datetime.now().isoformat(),
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(
                f"Error generating manual timelapse for {camera_name}: {e}"
            )
            raise HTTPException(status_code=500, detail=str(e))

    # ================================
    # TIMELAPSE CONTROL METHODS
    # ================================

    async def start_timelapse(self, camera_name: str) -> TimelapseControlResponse:
        """Start timelapse recording for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            success = self.camera_manager.start_timelapse(camera_name)
            if success:
                state = self.camera_manager.get_timelapse_state(camera_name)
                return TimelapseControlResponse(
                    status="success",
                    message=f"Timelapse started for camera {camera_name}",
                    camera_name=camera_name,
                    timelapse_state=state.value if state else "unknown",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to start timelapse for camera {camera_name}",
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error starting timelapse for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def pause_timelapse(self, camera_name: str) -> TimelapseControlResponse:
        """Pause timelapse recording for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            success = self.camera_manager.pause_timelapse(camera_name)
            if success:
                state = self.camera_manager.get_timelapse_state(camera_name)
                return TimelapseControlResponse(
                    status="success",
                    message=f"Timelapse paused for camera {camera_name}",
                    camera_name=camera_name,
                    timelapse_state=state.value if state else "unknown",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to pause timelapse for camera {camera_name}",
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error pausing timelapse for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def resume_timelapse(self, camera_name: str) -> TimelapseControlResponse:
        """Resume timelapse recording for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            success = self.camera_manager.resume_timelapse(camera_name)
            if success:
                state = self.camera_manager.get_timelapse_state(camera_name)
                return TimelapseControlResponse(
                    status="success",
                    message=f"Timelapse resumed for camera {camera_name}",
                    camera_name=camera_name,
                    timelapse_state=state.value if state else "unknown",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to resume timelapse for camera {camera_name}",
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error resuming timelapse for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def stop_timelapse(self, camera_name: str) -> TimelapseControlResponse:
        """Stop timelapse recording for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            success = self.camera_manager.stop_timelapse(camera_name)
            if success:
                state = self.camera_manager.get_timelapse_state(camera_name)
                return TimelapseControlResponse(
                    status="success",
                    message=f"Timelapse stopped for camera {camera_name}",
                    camera_name=camera_name,
                    timelapse_state=state.value if state else "unknown",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to stop timelapse for camera {camera_name}",
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error stopping timelapse for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def reset_timelapse(self, camera_name: str) -> TimelapseControlResponse:
        """Reset timelapse recording for the specified camera."""
        try:
            # Validate camera exists
            camera_config = self.camera_manager.get_camera_config(camera_name)
            if not camera_config:
                raise HTTPException(
                    status_code=404, detail=f"Camera {camera_name} not found"
                )

            success = self.camera_manager.reset_timelapse(camera_name)
            if success:
                state = self.camera_manager.get_timelapse_state(camera_name)
                return TimelapseControlResponse(
                    status="success",
                    message=f"Timelapse reset for camera {camera_name}",
                    camera_name=camera_name,
                    timelapse_state=state.value if state else "unknown",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to reset timelapse for camera {camera_name}",
                )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error resetting timelapse for {camera_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _get_camera_status_data(self) -> List[Dict[str, Any]]:
        """Get formatted camera status data."""
        cameras = []

        camera_configs = self.config.get_cameras_typed()
        for camera_config in camera_configs:
            camera_state = self.camera_manager.get_camera_state(camera_config.name)

            if camera_state:
                camera_data = self._camera_state_to_dict(camera_state)
                camera_data.update(
                    {
                        "url": camera_config.url,
                        "enabled": camera_config.enabled,
                        "rotation": camera_config.rotation.value,
                        "is_healthy": self.camera_manager.is_camera_healthy(
                            camera_config.name
                        ),
                        "last_image_path": self._get_latest_image_path(
                            camera_config.name
                        ),
                        "capture_stats": self._get_capture_stats(camera_state),
                        "latest_timelapse": self._get_latest_timelapse_info(
                            camera_config.name
                        ),
                    }
                )
                cameras.append(camera_data)

        return cameras

    def _camera_state_to_dict(self, camera_state: CameraState) -> Dict[str, Any]:
        """Convert camera state to dictionary."""
        return {
            "name": camera_state.name,
            "status": camera_state.status.value,
            "last_capture_time": (
                camera_state.last_capture_time.isoformat()
                if camera_state.last_capture_time
                else None
            ),
            "last_error": camera_state.last_error,
            "consecutive_failures": camera_state.consecutive_failures,
            "total_captures": camera_state.total_captures,
            "status_class": self._get_status_class(camera_state.status),
            "status_icon": self._get_status_icon(camera_state.status),
            "timelapse_state": camera_state.timelapse_state.value,
            "timelapse_frame_count": camera_state.timelapse_frame_count,
            "timelapse_started_at": (
                camera_state.timelapse_started_at.isoformat()
                if camera_state.timelapse_started_at
                else None
            ),
            "timelapse_paused_at": (
                camera_state.timelapse_paused_at.isoformat()
                if camera_state.timelapse_paused_at
                else None
            ),
        }

    def _get_status_class(self, status: CameraStatus) -> str:
        """Get CSS class for camera status."""
        return {
            CameraStatus.ONLINE: "success",
            CameraStatus.OFFLINE: "warning",
            CameraStatus.ERROR: "danger",
            CameraStatus.DISABLED: "secondary",
        }.get(status, "secondary")

    def _get_status_icon(self, status: CameraStatus) -> str:
        """Get icon name for camera status."""
        return {
            CameraStatus.ONLINE: "check-circle",
            CameraStatus.OFFLINE: "x-circle",
            CameraStatus.ERROR: "alert-triangle",
            CameraStatus.DISABLED: "pause-circle",
        }.get(status, "help-circle")

    def _get_latest_image_path(self, camera_name: str) -> Optional[str]:
        """Get path to the latest image for a camera."""
        try:
            storage_settings = self.config.get_storage_settings_typed()
            image_settings = self.config.get_image_settings_typed()
            frames_dir = Path(storage_settings.output_dir) / camera_name / "frames"

            if frames_dir.exists():
                image_files = list(
                    frames_dir.glob(
                        f"{camera_name}_*.{image_settings.image_type.value}"
                    )
                )
                if image_files:
                    latest_image = max(image_files, key=lambda x: x.stat().st_mtime)
                    return str(
                        latest_image.relative_to(Path(storage_settings.output_dir))
                    )
        except Exception as e:
            self.logger.debug(f"Error getting latest image for {camera_name}: {e}")
        return None

    def _get_latest_image_info(self, camera_name: str) -> Dict[str, Any]:
        """Get detailed info about the latest image."""
        latest_path = self._get_latest_image_path(camera_name)
        if not latest_path:
            return {"exists": False}

        try:
            storage_settings = self.config.get_storage_settings_typed()
            full_path = Path(storage_settings.output_dir) / latest_path
            stat = full_path.stat()

            return {
                "exists": True,
                "path": latest_path,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        except Exception as e:
            self.logger.debug(f"Error getting image info for {camera_name}: {e}")
            return {"exists": False}

    def _get_latest_timelapse_info(self, camera_name: str) -> Dict[str, Any]:
        """Get information about the latest timelapse for a camera."""
        try:
            storage_settings = self.config.get_storage_settings_typed()
            timelapse_settings = self.config.get_timelapse_settings_typed()

            # Check multiple timelapse directories
            timelapse_dirs = [
                Path(storage_settings.output_dir) / camera_name / "timelapses",
                Path(storage_settings.output_dir)
                / camera_name
                / "continuous_timelapses",
                Path(storage_settings.output_dir)
                / camera_name
                / "checkpoint_timelapses",
            ]

            latest_timelapse = None
            latest_time = 0
            timelapse_type = None

            for timelapse_dir in timelapse_dirs:
                if not timelapse_dir.exists():
                    continue

                timelapse_files = list(
                    timelapse_dir.glob(f"*.{timelapse_settings.timelapse_format.value}")
                )

                for timelapse_file in timelapse_files:
                    mtime = timelapse_file.stat().st_mtime
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_timelapse = timelapse_file
                        timelapse_type = timelapse_dir.name.replace("_", " ").title()

            if latest_timelapse:
                stat = latest_timelapse.stat()
                return {
                    "exists": True,
                    "filename": latest_timelapse.name,
                    "path": str(
                        latest_timelapse.relative_to(Path(storage_settings.output_dir))
                    ),
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "age": self._get_time_ago(datetime.fromtimestamp(stat.st_mtime)),
                    "type": timelapse_type,
                }
            else:
                return {"exists": False}

        except Exception as e:
            self.logger.error(
                f"Error getting latest timelapse info for {camera_name}: {e}"
            )
            return {"exists": False}

    def _get_capture_stats(self, camera_state: CameraState) -> Dict[str, Any]:
        """Get capture statistics for a camera."""
        success_rate = 0.0
        if camera_state.total_captures > 0:
            failures = camera_state.consecutive_failures
            success_rate = max(
                0,
                ((camera_state.total_captures - failures) / camera_state.total_captures)
                * 100,
            )

        # Calculate time since last capture
        last_capture_ago = "Never"
        if camera_state.last_capture_time:
            time_diff = datetime.now() - camera_state.last_capture_time
            if time_diff.total_seconds() < 60:
                last_capture_ago = f"{int(time_diff.total_seconds())}s ago"
            elif time_diff.total_seconds() < 3600:
                last_capture_ago = f"{int(time_diff.total_seconds() // 60)}m ago"
            else:
                last_capture_ago = f"{int(time_diff.total_seconds() // 3600)}h ago"

        # Calculate time until next capture
        capture_interval = self.config.get_capture_interval()
        next_capture_time, next_capture_in_seconds = calculate_next_capture_time(
            camera_state.last_capture_time, capture_interval
        )

        return {
            "success_rate": round(success_rate, 1),
            "last_capture_ago": last_capture_ago,
            "is_healthy": self.camera_manager.is_camera_healthy(camera_state.name),
            "next_capture_in_seconds": int(next_capture_in_seconds),
            "next_capture_time": (
                next_capture_time.isoformat() if next_capture_time else None
            ),
            "capture_interval": capture_interval,
        }

    def _get_time_ago(self, timestamp: datetime) -> str:
        """Get human-readable time ago string."""
        return get_time_ago(timestamp)

    def _get_camera_images(
        self, camera_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get list of recent images for a camera."""
        try:
            storage_settings = self.config.get_storage_settings_typed()
            image_settings = self.config.get_image_settings_typed()
            frames_dir = Path(storage_settings.output_dir) / camera_name / "frames"

            if not frames_dir.exists():
                return []

            image_files = list(
                frames_dir.glob(f"{camera_name}_*.{image_settings.image_type.value}")
            )
            image_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            images = []
            for img_file in image_files[:limit]:
                stat = img_file.stat()
                images.append(
                    {
                        "filename": img_file.name,
                        "path": str(
                            img_file.relative_to(Path(storage_settings.output_dir))
                        ),
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "age": self._get_time_ago(
                            datetime.fromtimestamp(stat.st_mtime)
                        ),
                    }
                )

            return images
        except Exception as e:
            self.logger.error(f"Error getting images for {camera_name}: {e}")
            return []

    def _get_capture_history(self, camera_name: str) -> Dict[str, Any]:
        """Get capture history for a camera."""
        # This is a placeholder - you could implement actual history tracking
        return {
            "last_24h": 0,  # Could count files from last 24h
            "last_week": 0,  # Could count files from last week
            "trend": "stable",  # Could analyze capture frequency trends
        }

    def _get_camera_storage_info(self, camera_name: str) -> Dict[str, Any]:
        """Get storage information for a camera."""
        try:
            storage_settings = self.config.get_storage_settings_typed()
            camera_dir = Path(storage_settings.output_dir) / camera_name

            if not camera_dir.exists():
                return {"total_size_mb": 0, "file_count": 0}

            total_size = 0
            file_count = 0

            for file_path in camera_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1

            return {
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "directory": str(camera_dir),
            }
        except Exception as e:
            self.logger.error(f"Error getting storage info for {camera_name}: {e}")
            return {"total_size_mb": 0, "file_count": 0}

    def _get_storage_statistics(self) -> Dict[str, Any]:
        """Get overall storage statistics."""
        try:
            storage_settings = self.config.get_storage_settings_typed()
            base_dir = Path(storage_settings.output_dir)

            if not base_dir.exists():
                return {"total_size_mb": 0, "total_files": 0}

            total_size = 0
            total_files = 0

            for file_path in base_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    total_files += 1

            return {
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "total_files": total_files,
                "base_directory": str(base_dir),
            }
        except Exception as e:
            self.logger.error(f"Error getting storage statistics: {e}")
            return {"total_size_mb": 0, "total_files": 0}

    def _get_uptime_seconds(self) -> int:
        """Get system uptime in seconds."""
        # This is a placeholder - you could track actual start time
        return 3600  # 1 hour placeholder


class UniFiTimeLapserWebServer:
    """
    FastAPI web server for camera status dashboard.

    Provides both REST API and web interface for monitoring cameras.
    """

    def __init__(
        self, config: Config, camera_manager: CameraManager, logger: logging.Logger
    ):
        """
        Initialize the web server.

        Args:
            config: Application configuration
            camera_manager: Camera manager service
            logger: Logger instance
        """
        self.config = config
        self.camera_manager = camera_manager
        self.logger = logger

        # Initialize timelapse service
        self.timelapse_service = TimelapseService(config, logger)

        # Initialize FastAPI app
        self.app = FastAPI(
            title="UniFi Timelapser API",
            description="Camera monitoring and timelapser management API",
            version="2.0.0",
            docs_url="/api/docs",
            redoc_url="/api/redoc",
        )

        # Initialize API
        self.api = UniFiTimelapserAPI(
            camera_manager, config, logger, self.timelapse_service
        )

        # Setup templates and static files
        self._setup_static_files()

        # Register routes
        self._register_api_routes()
        self._register_web_routes()

    def _setup_static_files(self) -> None:
        """Setup static file serving and templates."""
        # Get the web directory
        web_dir = Path(__file__).parent

        # Setup templates
        self.templates = Jinja2Templates(directory=str(web_dir / "templates"))

        # Mount static files
        self.app.mount(
            "/static", StaticFiles(directory=str(web_dir / "static")), name="static"
        )

    def _register_api_routes(self) -> None:
        """Register all API endpoints."""

        @self.app.get("/api/health", response_model=HealthStatusResponse)
        async def api_health():
            """System health check endpoint."""
            return await self.api.get_health_status()

        @self.app.get("/api/cameras", response_model=CameraListResponse)
        async def api_cameras_list():
            """Get list of all cameras with status."""
            return await self.api.get_cameras_list()

        @self.app.get("/api/cameras/{camera_name}", response_model=CameraDetailResponse)
        async def api_camera_detail(camera_name: str):
            """Get detailed information for a specific camera."""
            return await self.api.get_camera_detail(camera_name)

        @self.app.get(
            "/api/cameras/{camera_name}/images", response_model=ImageListResponse
        )
        async def api_camera_images(
            camera_name: str, limit: int = Query(10, ge=1, le=100)
        ):
            """Get list of recent images for a camera."""
            return await self.api.get_camera_images(camera_name, limit)

        @self.app.get("/api/stats", response_model=SystemStatsResponse)
        async def api_system_stats():
            """Get comprehensive system statistics."""
            return await self.api.get_system_stats()

        @self.app.put(
            "/api/cameras/{camera_name}/timelapse",
            response_model=ManualTimelapseResponse,
        )
        async def api_generate_manual_timelapse(
            camera_name: str,
            checkpoint: bool = Query(
                False, description="Generate as checkpoint timelapse"
            ),
        ):
            """Generate a manual timelapse for the specified camera."""
            return await self.api.generate_manual_timelapse(camera_name, checkpoint)

        # Timelapse control endpoints
        @self.app.post(
            "/api/cameras/{camera_name}/timelapse/start",
            response_model=TimelapseControlResponse,
        )
        async def api_start_timelapse(camera_name: str):
            """Start timelapse recording for the specified camera."""
            return await self.api.start_timelapse(camera_name)

        @self.app.post(
            "/api/cameras/{camera_name}/timelapse/pause",
            response_model=TimelapseControlResponse,
        )
        async def api_pause_timelapse(camera_name: str):
            """Pause timelapse recording for the specified camera."""
            return await self.api.pause_timelapse(camera_name)

        @self.app.post(
            "/api/cameras/{camera_name}/timelapse/resume",
            response_model=TimelapseControlResponse,
        )
        async def api_resume_timelapse(camera_name: str):
            """Resume timelapse recording for the specified camera."""
            return await self.api.resume_timelapse(camera_name)

        @self.app.post(
            "/api/cameras/{camera_name}/timelapse/stop",
            response_model=TimelapseControlResponse,
        )
        async def api_stop_timelapse(camera_name: str):
            """Stop timelapse recording for the specified camera."""
            return await self.api.stop_timelapse(camera_name)

        @self.app.post(
            "/api/cameras/{camera_name}/timelapse/reset",
            response_model=TimelapseControlResponse,
        )
        async def api_reset_timelapse(camera_name: str):
            """Reset timelapse recording for the specified camera."""
            return await self.api.reset_timelapse(camera_name)

    def _register_web_routes(self) -> None:
        """Register all web interface routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            """Main dashboard with camera status cards."""
            try:
                cameras = self.api._get_camera_status_data()
                config_summary = self._get_config_summary()
                system_stats = self.camera_manager.get_statistics()

                return self.templates.TemplateResponse(
                    "dashboard.html",
                    {
                        "request": request,
                        "cameras": cameras,
                        "config": config_summary,
                        "stats": system_stats,
                    },
                )
            except Exception as e:
                self.logger.error(f"Error rendering dashboard: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Error loading dashboard: {e}"
                )

        @self.app.get("/camera/{camera_name}", response_class=HTMLResponse)
        async def camera_detail(request: Request, camera_name: str):
            """Detailed view for a specific camera."""
            try:
                camera_state = self.camera_manager.get_camera_state(camera_name)
                camera_config = self.camera_manager.get_camera_config(camera_name)

                if not camera_state or not camera_config:
                    raise HTTPException(
                        status_code=404, detail=f"Camera {camera_name} not found"
                    )

                camera_data = self.api._camera_state_to_dict(camera_state)
                camera_data.update(
                    {
                        "url": camera_config.url,
                        "enabled": camera_config.enabled,
                        "rotation": camera_config.rotation.value,
                        "capture_stats": self.api._get_capture_stats(camera_state),
                        "latest_image": self.api._get_latest_image_info(camera_name),
                        "recent_images": self.api._get_camera_images(camera_name, 20),
                        "storage_info": self.api._get_camera_storage_info(camera_name),
                        "latest_timelapse": self.api._get_latest_timelapse_info(
                            camera_name
                        ),
                    }
                )

                return self.templates.TemplateResponse(
                    "camera_detail_tailwind.html",
                    {"request": request, "camera": camera_data},
                )
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(
                    f"Error rendering camera detail for {camera_name}: {e}"
                )
                raise HTTPException(
                    status_code=500, detail=f"Error loading camera details: {e}"
                )

        @self.app.get("/config", response_class=HTMLResponse)
        async def config_page(request: Request):
            """Configuration overview page."""
            try:
                config_data = self._get_detailed_config()
                return self.templates.TemplateResponse(
                    "config.html", {"request": request, "config": config_data}
                )
            except Exception as e:
                self.logger.error(f"Error rendering config page: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Error loading configuration: {e}"
                )

        @self.app.get("/logs", response_class=HTMLResponse)
        async def logs_page(request: Request):
            """System logs page."""
            try:
                recent_logs = self._get_recent_logs()
                return self.templates.TemplateResponse(
                    "logs.html", {"request": request, "logs": recent_logs}
                )
            except Exception as e:
                self.logger.error(f"Error rendering logs page: {e}")
                raise HTTPException(status_code=500, detail=f"Error loading logs: {e}")

        @self.app.get("/media/{filename:path}")
        async def serve_image(filename: str):
            """Serve camera images."""
            try:
                self.logger.debug(f"Serving image: {filename}")

                # FastAPI app runs from src/ directory, but media/ is at project root
                # Get the project root directory (parent of src/)
                current_dir = Path(__file__).parent  # web/
                src_dir = current_dir.parent  # src/
                project_root = src_dir.parent  # project root
                media_dir = project_root / "media"

                self.logger.debug(f"Project root: {project_root}")
                self.logger.debug(f"Media directory: {media_dir}")

                # Check if media directory exists
                if not media_dir.exists():
                    self.logger.error(f"Media directory does not exist: {media_dir}")
                    raise HTTPException(
                        status_code=404, detail="Media directory not found"
                    )

                # Check if the requested file exists
                requested_file_path = media_dir / filename
                self.logger.debug(f"Looking for file: {requested_file_path}")

                if not requested_file_path.exists():
                    self.logger.warning(f"Image not found: {requested_file_path}")
                    raise HTTPException(status_code=404, detail="Image not found")

                self.logger.debug(f"Successfully serving file: {requested_file_path}")
                return FileResponse(str(requested_file_path))

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error serving image {filename}: {e}")
                raise HTTPException(status_code=404, detail="Image not found")

    def _get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for the dashboard."""
        camera_configs = self.config.get_cameras_typed()
        image_settings = self.config.get_image_settings_typed()
        operational_settings = self.config.get_operational_settings_typed()
        timelapse_settings = self.config.get_timelapse_settings_typed()
        storage_settings = self.config.get_storage_settings_typed()

        return {
            "total_cameras": len(camera_configs),
            "enabled_cameras": len([c for c in camera_configs if c.enabled]),
            "image_format": image_settings.image_type.value,
            "frequency_minutes": operational_settings.frequency // 60,
            "timelapse_enabled": timelapse_settings.timelapse_enabled,
            "output_directory": str(storage_settings.output_dir),
            "cleanup_enabled": storage_settings.cleanup_days > 0,
            "cleanup_days": storage_settings.cleanup_days,
        }

    def _get_detailed_config(self) -> Dict[str, Any]:
        """Get detailed configuration for the config page."""
        camera_configs = self.config.get_cameras_typed()
        image_settings = self.config.get_image_settings_typed()
        operational_settings = self.config.get_operational_settings_typed()
        timelapse_settings = self.config.get_timelapse_settings_typed()
        storage_settings = self.config.get_storage_settings_typed()

        return {
            "cameras": {
                camera.name: {
                    "url": camera.url,
                    "enabled": camera.enabled,
                    "rotation": camera.rotation.value,
                }
                for camera in camera_configs
            },
            "capture": {
                "frequency_seconds": operational_settings.frequency,
                "image_format": image_settings.image_type.value,
                "image_width": image_settings.image_width,
                "image_height": image_settings.image_height,
                "output_directory": str(storage_settings.output_dir),
                "timezone": operational_settings.timezone,
                "time_window": f"{operational_settings.time_start} - {operational_settings.time_stop}",
            },
            "timelapse": {
                "enabled": timelapse_settings.timelapse_enabled,
                "frame_rate": timelapse_settings.timelapse_speed,
                "format": timelapse_settings.timelapse_format.value,
                "checkpoint_enabled": timelapse_settings.checkpoint_enabled,
            },
            "cleanup": {
                "cleanup_days": storage_settings.cleanup_days,
                "log_cleanup_days": storage_settings.log_cleanup_days,
                "cleanup_enabled": storage_settings.cleanup_days > 0,
            },
        }

    def _get_recent_logs(self, lines: int = 100) -> List[str]:
        """Get recent log entries."""
        try:
            log_file_path = self.config.get_log_file_path()
            log_path = Path(log_file_path)

            if not log_path.exists():
                return ["Log file not found"]

            with open(log_path, "r") as f:
                all_lines = f.readlines()

            # Return last N lines
            return [line.strip() for line in all_lines[-lines:]]
        except Exception as e:
            self.logger.error(f"Error reading logs: {e}")
            return [f"Error reading logs: {e}"]

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        return self.app
