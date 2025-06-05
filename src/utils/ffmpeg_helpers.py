#!/usr/bin/env python3
# src/utils/ffmpeg_helpers.py
"""
FFmpeg command building utilities for UniFi Timelapser.
Centralizes FFmpeg command construction to eliminate duplication.
"""

from typing import List, Optional, Union
import logging

__all__ = [
    "build_capture_command",
    "build_timelapse_command",
    "get_rotation_filter",
    "log_ffmpeg_command",
]


def build_capture_command(
    input_url: str,
    output_path: str,
    width: int = 0,
    height: int = 0,
    rotation_filter: Optional[str] = None,
    quality: str = "1",
    timeout: int = 30,
) -> List[str]:
    """
    Build FFmpeg command for image capture.

    Args:
        input_url: Camera RTSP/HTTP URL
        output_path: Output file path
        width: Image width (0 for original)
        height: Image height (0 for original)
        rotation_filter: FFmpeg rotation filter string
        quality: Video quality setting
        timeout: Timeout in seconds

    Returns:
        FFmpeg command as list of strings
    """
    command = [
        "ffmpeg",
        "-y",  # Overwrite output files
        "-rtsp_transport",
        "tcp",
        "-i",
        input_url,
        "-vframes",
        "1",  # Capture one frame
        "-q:v",
        quality,  # High quality
    ]

    # Add resolution if specified
    if width > 0 and height > 0:
        command.extend(["-s", f"{width}x{height}"])

    # Add rotation filter if specified
    if rotation_filter:
        command.extend(["-vf", rotation_filter])

    command.append(output_path)
    return command


def build_timelapse_command(
    input_pattern: str,
    output_path: str,
    framerate: int = 30,
    preset: str = "medium",
    crf: str = "23",
    rotation_filter: Optional[str] = None,
) -> List[str]:
    """
    Build FFmpeg command for timelapse creation.

    Args:
        input_pattern: Input file pattern (e.g., "/path/camera_*.jpg")
        output_path: Output video file path
        framerate: Video framerate
        preset: FFmpeg preset (ultrafast, fast, medium, slow, veryslow)
        crf: Constant Rate Factor (0-51, lower = better quality)
        rotation_filter: Optional rotation filter

    Returns:
        FFmpeg command as list of strings
    """
    command = [
        "ffmpeg",
        "-y",  # Overwrite output files
        "-framerate",
        str(framerate),
        "-pattern_type",
        "glob",
        "-i",
        input_pattern,
    ]

    # Add rotation filter if specified
    if rotation_filter:
        command.extend(["-vf", rotation_filter])

    # Add encoding options
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
    )

    return command


def get_rotation_filter(rotation_option: Optional[Union[str, int]]) -> Optional[str]:
    """
    Get FFmpeg rotation filter string.

    Args:
        rotation_option: Rotation option (str or int)

    Returns:
        FFmpeg filter string or None
    """
    if rotation_option is None:
        return None

    rotation_map = {
        "none": None,
        "left": "transpose=2",  # 90 degrees counterclockwise
        "right": "transpose=1",  # 90 degrees clockwise
        "invert": "transpose=1,transpose=1",  # 180 degrees
        0: None,
        90: "transpose=1",  # 90 degrees clockwise
        180: "transpose=1,transpose=1",  # 180 degrees
        270: "transpose=2",  # 90 degrees counterclockwise
        -90: "transpose=2",  # 90 degrees counterclockwise
    }

    # Normalize string input
    if isinstance(rotation_option, str):
        processed_option = rotation_option.lower().strip()
    else:
        processed_option = rotation_option

    return rotation_map.get(processed_option)


def log_ffmpeg_command(
    command: List[str], logger: logging.Logger, camera_name: str = ""
) -> None:
    """
    Log FFmpeg command in a readable format.

    Args:
        command: FFmpeg command list
        logger: Logger instance
        camera_name: Optional camera name for context
    """
    # Only log first 10 elements to avoid cluttering logs with long paths
    cmd_preview = " ".join(command[:10])
    if len(command) > 10:
        cmd_preview += "..."

    prefix = f"[{camera_name}] " if camera_name else ""
    logger.debug(f"{prefix}Executing FFmpeg: {cmd_preview}")
