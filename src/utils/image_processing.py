#!/usr/bin/env python3
# src/utils/image_processing.py
"""
Image processing utilities for UniFi Timelapser.
Handles image capture from cameras, rotation, and compression.
"""

import subprocess
from pathlib import Path
from typing import Optional, Union
import time
import logging

from PIL import Image, UnidentifiedImageError
from .time_helpers import (
    parse_timezone,
    create_timestamped_name,
    get_current_time_in_tz,
)
from .path_helpers import ensure_directory_exists
from .ffmpeg_helpers import (
    build_capture_command,
    get_rotation_filter,
    log_ffmpeg_command,
)
from .constants import (
    FFMPEG_TIMEOUT_SECONDS,
    DEFAULT_CAPTURE_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_COMPRESSION_QUALITY,
    MIN_COMPRESSION_QUALITY,
    COMPRESSION_QUALITY_STEP,
)


def capture_image_from_camera(
    camera_name: str,
    camera_url: str,
    output_dir: Path,
    image_type: str,
    rotate_option: Optional[Union[str, int]],
    logger: logging.Logger,
    # Image settings parameters
    retries: int = DEFAULT_CAPTURE_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY_SECONDS,
    image_width: int = 0,
    image_height: int = 0,
    timezone_str: str = "UTC",
    max_image_size: int = 0,
    compression_quality: int = DEFAULT_COMPRESSION_QUALITY,
) -> Optional[Path]:
    """
    Captures an image from a camera URL using FFmpeg, saves it.

    Args:
        camera_name: The name of the camera (for logging and filename prefix).
        camera_url: The RTSP or HTTP URL of the camera stream.
        output_dir: The base directory where the camera's images should be stored.
        image_type: The desired image format (e.g., "jpg", "png").
        rotate_option: Rotation option (Union[str, int] or None).
        logger: Logger instance for logging.
        retries: Number of capture retry attempts.
        retry_delay: Sleep duration between retries in seconds.
        image_width: Image width (0 for original).
        image_height: Image height (0 for original).
        timezone_str: Timezone string for timestamp generation.
        max_image_size: Max image size in KB (0 for no compression).
        compression_quality: JPEG compression quality.

    Returns:
        The Path to the captured image if successful, None otherwise.
    """

    # Ensure output directory exists
    if not ensure_directory_exists(output_dir, logger):
        return None

    # Create timestamped filename using centralized helper
    timestamp = get_current_time_in_tz(timezone_str, logger)
    filename = create_timestamped_name(
        camera_name, timestamp, timezone_str, image_type, logger
    )
    current_output_path = output_dir / filename

    # Get rotation filter
    rotation_filter = get_rotation_filter(rotate_option)

    # Build FFmpeg command using helper
    ffmpeg_command = build_capture_command(
        input_url=camera_url,
        output_path=str(current_output_path),
        width=image_width,
        height=image_height,
        rotation_filter=rotation_filter,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )

    # Retry logic
    for attempt in range(1, retries + 1):
        log_ffmpeg_command(ffmpeg_command, logger, camera_name)

        try:
            result = subprocess.run(
                ffmpeg_command,
                capture_output=True,
                text=True,
                timeout=FFMPEG_TIMEOUT_SECONDS,
            )

            if result.returncode == 0 and current_output_path.exists():
                file_size = current_output_path.stat().st_size
                if file_size > 0:
                    logger.info(
                        f"[{camera_name}] Successfully captured image: {current_output_path} ({file_size} bytes)"
                    )

                    # Apply compression if needed
                    if max_image_size > 0:
                        compressed_path = compress_image_file(
                            image_path=current_output_path,
                            max_size_kb=max_image_size,
                            camera_name=camera_name,
                            logger=logger,
                            compression_quality=compression_quality,
                            compression_enabled=True,
                        )
                        return compressed_path

                    return current_output_path
                else:
                    logger.warning(f"[{camera_name}] Captured image is empty (0 bytes)")
            else:
                logger.error(
                    f"[{camera_name}] FFmpeg failed (attempt {attempt}/{retries}). "
                    f"Return code: {result.returncode}"
                )
                if result.stderr:
                    logger.error(f"[{camera_name}] FFmpeg stderr: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error(
                f"[{camera_name}] FFmpeg timeout after {FFMPEG_TIMEOUT_SECONDS} seconds (attempt {attempt}/{retries})"
            )
        except Exception as e:
            logger.error(
                f"[{camera_name}] Unexpected error during capture (attempt {attempt}/{retries}): {e}"
            )

        # Sleep before retry (except on last attempt)
        if attempt < retries:
            logger.debug(
                f"[{camera_name}] Waiting {retry_delay} seconds before retry..."
            )
            time.sleep(retry_delay)

    logger.error(f"[{camera_name}] Failed to capture image after {retries} attempts.")

    # Clean up empty file if it exists
    if current_output_path.exists() and current_output_path.stat().st_size == 0:
        try:
            current_output_path.unlink(missing_ok=True)
            logger.info(
                f"[{camera_name}] Deleted zero-byte file: {current_output_path}"
            )
        except OSError as e_del:
            logger.error(
                f"[{camera_name}] Error deleting zero-byte file {current_output_path}: {e_del}"
            )

    return None


def compress_image_file(
    image_path: Path,
    max_size_kb: int,
    camera_name: str,
    logger: logging.Logger,
    compression_quality: int = DEFAULT_COMPRESSION_QUALITY,
    compression_enabled: bool = True,
) -> Optional[Path]:
    """
    Compresses an image to ensure it does not exceed max_size_kb.
    Handles JPEG compression with quality adjustment.

    Args:
        image_path: Path to the image file to compress.
        max_size_kb: Maximum allowed file size in KB.
        camera_name: Camera name for logging.
        logger: Logger instance.
        compression_quality: Starting JPEG quality (1-100).
        compression_enabled: Whether compression is enabled.

    Returns:
        Path to the compressed image (same as input) or None on error.
    """
    if not image_path.exists():
        logger.error(f"[{camera_name}] Image to compress does not exist: {image_path}")
        return None

    if not compression_enabled:
        logger.debug(
            f"[{camera_name}] Compression is disabled. Returning original image path."
        )
        return image_path

    try:
        with Image.open(image_path) as img:
            original_size_kb = image_path.stat().st_size / 1024
            logger.debug(
                f"[{camera_name}] Original image size: {original_size_kb:.2f} KB"
            )

            if original_size_kb <= max_size_kb:
                logger.debug(
                    f"[{camera_name}] Image already within size limit ({max_size_kb} KB)"
                )
                return image_path

            # Only compress JPEG files for now
            # TODO: Need to compress PNGs etc
            if image_path.suffix.lower() not in [".jpg", ".jpeg"]:
                logger.debug(
                    f"[{camera_name}] Non-JPEG file, compression not implemented"
                )
                return image_path

            # Try different quality levels
            temp_path = image_path.with_suffix(f".comp_temp{image_path.suffix}")
            quality = compression_quality

            while quality >= MIN_COMPRESSION_QUALITY:
                logger.debug(f"[{camera_name}] Trying JPEG quality {quality}")
                img.save(temp_path, quality=quality, optimize=True)
                new_size_kb = temp_path.stat().st_size / 1024

                if new_size_kb <= max_size_kb:
                    # Success! Replace original with compressed version
                    temp_path.replace(image_path)
                    logger.info(
                        f"[{camera_name}] Compressed {image_path.name} from {original_size_kb:.2f} KB to {new_size_kb:.2f} KB (quality {quality})"
                    )
                    return image_path

                quality -= COMPRESSION_QUALITY_STEP

            # Cleanup temp file if compression failed
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

            logger.warning(
                f"[{camera_name}] Could not compress {image_path.name} to under {max_size_kb} KB"
            )
            return image_path

    except UnidentifiedImageError:
        logger.error(f"[{camera_name}] Cannot identify image file {image_path}")
        return None
    except Exception as e:
        logger.error(f"[{camera_name}] Error during compression: {e}", exc_info=True)
        return None
