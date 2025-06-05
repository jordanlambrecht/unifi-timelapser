#!/usr/bin/env python3
# src/core/service_container.py
"""
Dependency injection container
"""

from typing import Optional, Dict, Any, Callable, TypeVar, Type
import logging

from .config import Config, create_config
from .logger_setup import create_logger

T = TypeVar("T")


class ServiceContainer:
    """Dependency injection container with automatic service resolution"""

    def __init__(
        self, config: Optional[Config] = None, logger: Optional[logging.Logger] = None
    ):
        """
        Initialize service container with optional core dependencies.

        Args:
            config: Configuration instance (will be created if None)
            logger: Logger instance (will be created if None)
        """
        self._services: Dict[type, Any] = {}
        self._factories: Dict[type, Callable] = {}
        self._singletons: Dict[type, Any] = {}

        # Register core dependencies
        self._config = config or create_config()
        self._logger = logger or create_logger()

        self.register_singleton(Config, self._config)
        self.register_singleton(logging.Logger, self._logger)

        # Auto-register service factories
        self._register_service_factories()

    def register(self, service_type: Type[T], instance: T) -> None:
        """Register a service instance"""
        self._services[service_type] = instance

    def register_singleton(self, service_type: Type[T], instance: T) -> None:
        """Register a singleton service instance"""
        self._singletons[service_type] = instance

    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory function for lazy initialization"""
        self._factories[service_type] = factory

    def get(self, service_type: Type[T]) -> T:
        """Get a service instance, creating it if necessary"""
        # Check singletons first
        if service_type in self._singletons:
            return self._singletons[service_type]

        # Check regular services
        if service_type in self._services:
            return self._services[service_type]

        # Check factories
        if service_type in self._factories:
            instance = self._factories[service_type]()
            self._services[service_type] = instance
            return instance

        raise ValueError(f"Service {service_type} not registered")

    def has(self, service_type: type) -> bool:
        """Check if a service is registered"""
        return (
            service_type in self._services
            or service_type in self._factories
            or service_type in self._singletons
        )

    def clear(self) -> None:
        """Clear all registered services (useful for testing)"""
        self._services.clear()
        self._factories.clear()
        # Don't clear singletons as they include core dependencies

    def _register_service_factories(self) -> None:
        """Register all service factories with dependency injection."""
        try:
            # Import services dynamically to avoid circular imports
            from services.camera_manager import CameraManager
            from services.timelapse_service import TimelapseService
            from services.timelapse_orchestrator_service import (
                TimelapseOrchestratorService,
            )
            from services.capture_service import CaptureService
            from services.cleanup_service import CleanupService
            from database.connection import DatabaseManager, get_database_manager
            from database.database_services import DatabaseService

            # Register DatabaseManager if database is enabled
            config = self.get(Config)
            validated_config = config.get_validated_config()
            if validated_config and validated_config.database_settings.enabled:
                self.register_singleton(
                    DatabaseManager,
                    get_database_manager(validated_config.database_settings),
                )

                # Register DatabaseService
                self.register_factory(DatabaseService, lambda: DatabaseService())

            # Register CameraManager
            self.register_factory(
                CameraManager,
                lambda: CameraManager(
                    self.get(Config),
                    self.get(logging.Logger),
                    self.get(DatabaseManager) if self.has(DatabaseManager) else None,
                ),
            )

            # Register CaptureService
            self.register_factory(
                CaptureService,
                lambda: CaptureService(
                    self.get(Config),
                    self.get(logging.Logger),
                ),
            )

            # Register TimelapseService
            self.register_factory(
                TimelapseService,
                lambda: TimelapseService(
                    self.get(Config),
                    self.get(logging.Logger),
                ),
            )

            # Register TimelapseOrchestratorService with all dependencies
            self.register_factory(
                TimelapseOrchestratorService,
                lambda: TimelapseOrchestratorService(
                    self.get(Config),
                    self.get(CameraManager),
                    self.get(TimelapseService),
                    self.get(logging.Logger),
                ),
            )

            # Register CleanupService
            self.register_factory(
                CleanupService,
                lambda: CleanupService(
                    self.get(Config),
                    self.get(logging.Logger),
                ),
            )

        except ImportError as e:
            self._logger.warning(f"Could not import service: {e}")


def setup_container(
    config_file_path: Optional[str] = None,
    config: Optional[Config] = None,
    logger: Optional[logging.Logger] = None,
) -> ServiceContainer:
    """
    Setup and configure the service container with all dependencies.

    Args:
        config_file_path: Path to config file (used if config not provided)
        config: Existing config instance (optional)
        logger: Existing logger instance (optional)

    Returns:
        Configured service container
    """
    # Custom instruction test: Python function generated!
    # Create config if not provided
    if not config:
        config = create_config(config_file_path)

    # Create logger if not provided
    if not logger:
        logger = create_logger()

    return ServiceContainer(config, logger)


def create_container_for_testing(
    config: Config, logger: logging.Logger
) -> ServiceContainer:
    """
    Create a service container specifically for testing with mock dependencies.

    Args:
        config: Test configuration
        logger: Test logger

    Returns:
        Test service container
    """
    return ServiceContainer(config, logger)
