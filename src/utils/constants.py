#!/usr/bin/env python3
# src/utils/constants.py
"""
Constants and default values for UniFi Timelapser.
Centralizes hard-coded values to eliminate magic numbers.
"""

# FFmpeg defaults
FFMPEG_TIMEOUT_SECONDS = 30
FFMPEG_DEFAULT_QUALITY = "1"
FFMPEG_DEFAULT_PRESET = "medium"
FFMPEG_DEFAULT_CRF = "23"

# Image capture defaults
DEFAULT_IMAGE_TYPE = "png"
DEFAULT_CAPTURE_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 5

# Compression defaults
DEFAULT_COMPRESSION_QUALITY = 75
MIN_COMPRESSION_QUALITY = 10
COMPRESSION_QUALITY_STEP = 5

# Timelapse defaults
DEFAULT_TIMELAPSE_FPS = 30
DEFAULT_TIMELAPSE_FORMAT = "mp4"

# Directory names
FRAMES_SUBDIR = "frames"
TIMELAPSES_SUBDIR = "timelapses"
CHECKPOINT_TIMELAPSES_SUBDIR = "checkpoint_timelapses"
CONTINUOUS_TIMELAPSES_SUBDIR = "continuous_timelapses"

# Standard subdirectories for cameras
CAMERA_SUBDIRS = [
    FRAMES_SUBDIR,
    TIMELAPSES_SUBDIR,
    CHECKPOINT_TIMELAPSES_SUBDIR,
    CONTINUOUS_TIMELAPSES_SUBDIR,
]

# Cleanup defaults
DEFAULT_CLEANUP_DAYS = 30
DEFAULT_LOG_CLEANUP_DAYS = 7

# Health check defaults
DEFAULT_HEALTH_CHECK_INTERVAL = 300
DEFAULT_UNHEALTHY_THRESHOLD = 3

# Operational defaults
DEFAULT_CAPTURE_FREQUENCY = 900  # 15 minutes
DEFAULT_TIME_WINDOW = "00:00"  # 24/7

# File patterns
IMAGE_PATTERNS = {"jpg": "*.jpg", "jpeg": "*.jpeg", "png": "*.png", "webp": "*.webp"}

# Logging defaults
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "unifi_timelapser.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 5

# Timezone defaults
DEFAULT_TIMEZONE = "UTC"

# Thread and async defaults
SHUTDOWN_CHECK_INTERVAL = 0.1  # How often to check shutdown flag
MAIN_LOOP_SLEEP_CHUNKS = 10  # Break sleep into chunks for responsiveness
