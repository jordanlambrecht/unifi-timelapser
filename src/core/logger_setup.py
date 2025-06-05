#!/usr/bin/env python3
# src/core/logger_setup.py
"""
Logging setup for UniFi Timelapser with dependency injection support.
No global logger instances - all loggers are created and injected as dependencies.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pytz
from pathlib import Path
from typing import Optional
from utils import path_helpers


def create_logger(
    name: str = "UniFiTimelapseLogger",
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    log_file: Optional[str] = None,
    timezone_str: Optional[str] = None,
) -> logging.Logger:
    """
    Create a configured logger instance.

    Args:
        name: Logger name
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_file: Log file name
        timezone_str: Timezone string for log timestamps

    Returns:
        Configured logger instance
    """
    # Create logger instance
    logger = logging.getLogger(name)

    # Clear existing handlers to prevent duplication
    logger.handlers.clear()

    # Get configuration with defaults
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = log_dir or os.getenv("LOG_DIR", "logs")
    log_file = log_file or os.getenv("LOG_FILE", "unifi_timelapser.log")
    timezone_str = timezone_str or os.getenv("TZ", "UTC")

    # Set logger level
    try:
        logger.setLevel(getattr(logging, log_level))
    except AttributeError:
        logger.setLevel(logging.INFO)

    # Create log directory if it doesn't exist
    log_dir_path = Path(log_dir)
    path_helpers.ensure_directory_exists(log_dir_path)
    log_file_path = log_dir_path / log_file

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logger.level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5  # 5MB
        )
        file_handler.setLevel(logger.level)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except Exception as e:
        # If file logging fails, continue with console only
        logger.error(f"Failed to setup file logging: {e}")

    # Set timezone for logging
    try:
        tz = pytz.timezone(timezone_str)
        logging.Formatter.converter = lambda *args: datetime.now(tz=tz).timetuple()
    except pytz.UnknownTimeZoneError:
        # Default to UTC if timezone is invalid
        logging.Formatter.converter = lambda *args: datetime.now(
            tz=pytz.UTC
        ).timetuple()

    logger.info(f"Logger initialized - Level: {log_level}, File: {log_file_path}")
    return logger
