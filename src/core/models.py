#!/usr/bin/env python3
# src/core/models.py
"""
Consolidated models and data structures for UniFi Timelapser.
Contains all enums, domain models, and Pydantic configuration models in one place.
"""

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field, field_validator
import pytz


# ================================
# ENUMS - All enumeration types
# ================================


class CameraStatus(Enum):
    """Camera operational status"""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    DISABLED = "disabled"


class RotationOption(str, Enum):
    """Valid rotation options for camera images"""

    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    INVERT = "invert"


class ImageFormat(str, Enum):
    """Valid image formats"""

    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"


class VideoFormat(str, Enum):
    """Valid video formats for timelapses"""

    MP4 = "mp4"
    MOV = "mov"
    WEBM = "webm"


class LogLevel(str, Enum):
    """Valid log levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CaptureResult(Enum):
    """Result status of a capture operation"""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TimelapseStatus(Enum):
    """Status of timelapse creation operations"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TimelapseState(Enum):
    """State of timelapse control operations"""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


# ================================
# DOMAIN MODELS
# ================================


@dataclass
class CameraState:
    """Current operational state of a camera"""

    name: str
    status: CameraStatus
    last_capture_time: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    total_captures: int = 0
    timelapse_state: TimelapseState = TimelapseState.STOPPED
    timelapse_frame_count: int = 0
    timelapse_started_at: Optional[datetime] = None
    timelapse_paused_at: Optional[datetime] = None


@dataclass
class CaptureAttempt:
    """Details about a single image capture attempt"""

    camera_name: str
    timestamp: datetime
    result: CaptureResult
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None


@dataclass
class TimelapseJob:
    """Represents a timelapse creation job"""

    camera_name: str
    created_at: datetime
    status: TimelapseStatus
    input_directory: str
    output_file: Optional[str] = None
    frame_count: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ================================
# PYDANTIC CONFIG MODELS
# ================================


class CameraSettings(BaseModel):
    """Configuration for individual camera settings"""

    name: str = Field(..., min_length=1, description="Camera name")
    url: str = Field(..., min_length=1, description="RTSP URL for the camera")
    enabled: bool = Field(True, description="Whether this camera is enabled")
    rotation: RotationOption = Field(
        RotationOption.NONE, description="Image rotation option"
    )


class ImageSettings(BaseModel):
    """Image capture and processing settings"""

    image_type: ImageFormat = Field(
        default=ImageFormat.PNG, description="Output image format"
    )
    image_width: int = Field(
        default=0, ge=0, description="Image width (0 for original)"
    )
    image_height: int = Field(
        default=0, ge=0, description="Image height (0 for original)"
    )
    image_compression_quality: int = Field(
        default=75, ge=1, le=100, description="JPEG compression quality"
    )
    image_compress_quality_step: int = Field(
        default=5, ge=1, le=50, description="Quality reduction step during compression"
    )
    max_image_size: int = Field(
        default=0, ge=0, description="Max image size in KB (0 for no compression)"
    )
    image_capture_retries: int = Field(
        default=3, ge=0, le=10, description="Number of retry attempts for image capture"
    )
    image_capture_sleep: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Sleep duration between capture retries in seconds",
    )


class TimelapseGenerationMode(str, Enum):
    """Valid timelapse generation modes"""

    EVERY_CAPTURE = "every_capture"
    PERIODIC = "periodic"
    MANUAL_ONLY = "manual_only"


class TimelapseSettings(BaseModel):
    """Timelapse creation settings"""

    timelapse_enabled: bool = Field(
        default=True, description="Enable/disable continuous timelapse generation"
    )
    checkpoint_enabled: bool = Field(
        default=True, description="Enable/disable daily checkpoint timelapse generation"
    )
    timelapse_generation_frequency: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="Generate timelapse every N seconds (300s-24h)",
    )
    timelapse_generation_mode: TimelapseGenerationMode = Field(
        default=TimelapseGenerationMode.PERIODIC,
        description="When to generate timelapses: every_capture, periodic, or manual_only",
    )
    continuous_timelapse_max_age_hours: int = Field(
        default=24,
        ge=0,
        description="Keep continuous timelapses for N hours (0 for unlimited)",
    )
    max_timelapse_size: int = Field(
        default=0,
        ge=0,
        description="Max continuous timelapse file size in MB (0 for unlimited)",
    )
    timelapse_format: VideoFormat = Field(
        default=VideoFormat.MP4, description="Timelapse video format"
    )
    timelapse_speed: int = Field(
        default=30, ge=1, le=120, description="Frame rate for timelapse video in fps"
    )
    timelapse_max_images: int = Field(
        default=0,
        ge=0,
        description="Maximum images to include in timelapse (0 for unlimited)",
    )
    timelapse_width: int = Field(
        default=0, ge=0, description="Timelapse video width (0 for original)"
    )
    timelapse_height: int = Field(
        default=0, ge=0, description="Timelapse video height (0 for original)"
    )
    delete_images_after_timelapse: bool = Field(
        default=False,
        description="Delete source images after successful timelapse creation",
    )


class HealthCheckSettings(BaseModel):
    """Health check configuration"""

    health_check_interval: int = Field(
        default=300, ge=30, le=3600, description="Health check interval in seconds"
    )
    unhealthy_threshold: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of consecutive failures before marking unhealthy",
    )
    http_server_enabled: bool = Field(
        default=False, description="Enable HTTP health check server"
    )
    http_server_port: Optional[int] = Field(
        default=None, ge=1, le=65535, description="Port for HTTP health check server"
    )


class ApiServerSettings(BaseModel):
    """API server configuration"""

    enabled: bool = Field(default=False, description="Enable API server")
    api_port: int = Field(
        default=8080, ge=1, le=65535, description="Port for the Flask API server"
    )
    gunicorn_workers: int = Field(
        default=1, ge=1, le=16, description="Number of Gunicorn worker processes"
    )
    gunicorn_threads: int = Field(
        default=1, ge=1, le=32, description="Number of threads per worker"
    )


class WebDashboardSettings(BaseModel):
    """Web dashboard configuration"""

    enabled: bool = Field(default=True, description="Enable web dashboard")
    port: int = Field(
        default=5000, ge=1, le=65535, description="Port for the web dashboard"
    )
    host: str = Field(
        default="0.0.0.0", description="Host to bind the web dashboard to"
    )


class StorageSettings(BaseModel):
    """Storage and file management settings"""

    output_dir: str = Field(
        default="/media", description="Base directory for images and timelapses"
    )
    log_dir: str = Field(default="/logs", description="Directory for log files")
    log_file: str = Field(
        default="unifi_timelapser.log", description="Name of the log file"
    )
    cleanup_days: int = Field(
        default=30,
        ge=0,
        description="Delete images older than this many days (0 to disable)",
    )
    log_cleanup_days: int = Field(
        default=7,
        ge=0,
        description="Delete logs older than this many days (0 to disable)",
    )


class OperationalSettings(BaseModel):
    """Operational time and scheduling settings"""

    frequency: int = Field(
        default=900,
        ge=60,
        le=86400,
        description="Frequency of image capture in seconds",
    )
    time_start: str = Field(
        default="00:00",
        pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="Daily start time (HH:MM format)",
    )
    time_stop: str = Field(
        default="00:00",
        pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="Daily stop time (HH:MM format)",
    )
    timezone: str = Field(
        default="America/Chicago", description="Timezone for logging and operations"
    )
    config_reload_interval: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="Interval to check for config changes (0 to disable)",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        """Validate that the timezone is a valid pytz timezone"""
        try:
            pytz.timezone(v)
            return v
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {v}")

    @field_validator("time_start", "time_stop")
    @classmethod
    def validate_time_format(cls, v):
        """Validate that time strings can be parsed"""
        try:
            time.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid time format: {v}. Expected HH:MM format.")


class DatabaseSettings(BaseModel):
    """Database configuration settings"""

    enabled: bool = Field(default=True, description="Enable database functionality")
    database_url: Optional[str] = Field(
        default=None,
        description="Complete database URL (overrides individual settings)",
    )
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    database: str = Field(default="timelapser", description="Database name")
    username: str = Field(default="timelapser", description="Database username")
    password: str = Field(default="", description="Database password")

    # Connection pool settings
    pool_size: int = Field(default=5, ge=1, le=50, description="Connection pool size")
    max_overflow: int = Field(
        default=10, ge=0, le=50, description="Max overflow connections"
    )
    pool_timeout: int = Field(
        default=30, ge=5, le=300, description="Pool timeout in seconds"
    )
    pool_recycle: int = Field(
        default=3600, ge=300, le=86400, description="Pool recycle time in seconds"
    )

    # Migration settings
    auto_migrate: bool = Field(
        default=True, description="Automatically run migrations on startup"
    )

    @property
    def url(self) -> str:
        """Generate database URL from settings"""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_url(self) -> str:
        """Generate async database URL from settings"""
        if self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class UniFiTimelapserConfig(BaseModel):
    """Complete configuration model for UniFi Timelapser"""

    # Core settings
    image_settings: ImageSettings = Field(default_factory=ImageSettings)
    timelapse_settings: TimelapseSettings = Field(default_factory=TimelapseSettings)
    database_settings: DatabaseSettings = Field(default_factory=DatabaseSettings)
    health_check_settings: HealthCheckSettings = Field(
        default_factory=HealthCheckSettings
    )
    api_server_settings: ApiServerSettings = Field(default_factory=ApiServerSettings)
    web_dashboard_settings: WebDashboardSettings = Field(
        default_factory=WebDashboardSettings
    )
    storage_settings: StorageSettings = Field(default_factory=StorageSettings)
    operational_settings: OperationalSettings = Field(
        default_factory=OperationalSettings
    )

    # Camera configuration
    cameras: List[CameraSettings] = Field(
        default_factory=list, description="List of camera configurations"
    )


# ================================
# VALIDATION FUNCTIONS
# ================================


def validate_config_data(config_data: Dict[str, Any]) -> UniFiTimelapserConfig:
    """
    Validate configuration data using Pydantic models.

    Args:
        config_data: Raw configuration data from YAML/environment

    Returns:
        Validated configuration model

    Raises:
        ValidationError: If configuration is invalid
    """
    return UniFiTimelapserConfig(**config_data)
