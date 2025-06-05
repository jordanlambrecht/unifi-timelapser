#!/usr/bin/env python3
# src/core/interfaces.py
"""
Protocol interfaces for UniFi Timelapser dependency injection.
Defines contracts for services to improve testability and modularity.
"""

from typing import Protocol, Optional, Dict, Any, List
from pathlib import Path


class CameraServiceProtocol(Protocol):
    """Protocol for camera-related services"""

    def capture_image(self, camera_name: str) -> bool:
        """Capture an image from the specified camera"""
        ...

    def is_enabled(self, camera_name: str) -> bool:
        """Check if the camera is enabled"""
        ...


class FileManagerProtocol(Protocol):
    """Protocol for file management services"""

    def save_image(self, image_data: bytes, camera_name: str) -> Optional[Path]:
        """Save image data to disk"""
        ...

    def cleanup_old_files(self, camera_name: str) -> int:
        """Clean up old files and return count of deleted files"""
        ...


class ConfigProtocol(Protocol):
    """Protocol for configuration services"""

    def get_camera_config(self, camera_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific camera"""
        ...

    def get_cameras(self) -> Dict[str, Any]:
        """Get all camera configurations"""
        ...

    def reload(self) -> bool:
        """Reload configuration from file"""
        ...


class TimelapseServiceProtocol(Protocol):
    """Protocol for timelapse creation services"""

    def create_timelapse(
        self, camera_name: str, checkpoint: bool = False
    ) -> Optional[Path]:
        """Create a timelapse video for the specified camera"""
        ...


class CameraManagerProtocol(Protocol):
    """Protocol for camera management services"""

    def get_enabled_cameras(self) -> List[Any]:
        """Get list of enabled camera configurations"""
        ...

    def capture_all_cameras_sync(self) -> Dict[str, Optional[Path]]:
        """Capture images from all cameras synchronously"""
        ...

    def get_camera_summary(self) -> Dict[str, Dict]:
        """Get summary of all camera states"""
        ...
