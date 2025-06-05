#!/usr/bin/env python3
# src/main.py
"""
Simplified UniFi Timelapser main application.
- Simple threading approach (no APScheduler)
- No Flask API (focus on core functionality)
- Basic error logging (no complex health monitoring)
- Clean, focused architecture with dependency injection
- No global singletons - proper dependency management
"""

import signal
import sys
import threading
import time
import logging
from typing import Optional, NoReturn, Any

# Import dependency injection setup
from core.logger_setup import create_logger
from core.config import create_config, Config
from core.service_container import setup_container, ServiceContainer
from services.timelapse_orchestrator_service import TimelapseOrchestratorService
from services.camera_manager import CameraManager
from web.fastapi_web_server import UniFiTimeLapserWebServer
from services.cleanup_service import CleanupService
from utils.file_management import initialize_all_camera_storage
import uvicorn


class ApplicationManager:
    """Application manager that handles all services and dependencies."""

    def __init__(self):
        self.config: Optional[Config] = None
        self.logger: Optional[logging.Logger] = None
        self.container: Optional[ServiceContainer] = None
        self.shutdown_flag = threading.Event()

        # Thread references
        self.timelapser_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None
        self.web_server_thread: Optional[threading.Thread] = None

    def initialize(self) -> bool:
        """Initialize all application dependencies."""
        try:
            # Initialize core dependencies
            self.config = create_config()
            self.logger = create_logger()

            self.logger.info("🚀 Starting UniFi Timelapser (Simplified)")
            self.logger.info("=" * 50)

            # Validate configuration
            if not self.config.is_config_valid():
                errors = self.config.get_validation_errors()
                self.logger.error("❌ Configuration validation failed:")
                for error in errors:
                    self.logger.error(f"   {error}")
                return False

            self.logger.info("✅ Configuration validation passed")

            # Initialize storage directories
            self.logger.info("Initializing camera storage directories...")
            initialize_all_camera_storage(self.config, self.logger)
            self.logger.info("✅ Storage directories initialized")

            # Check camera configuration
            cameras = self.config.get_cameras_typed()
            if not cameras:
                self.logger.warning("⚠️  No cameras configured - check your config file")
                self.logger.info(
                    "Application will continue but no images will be captured"
                )
            else:
                self.logger.info(f"📷 Found {len(cameras)} configured cameras")

            # Initialize service container with dependencies
            self.logger.info("Setting up service container...")
            self.container = setup_container()
            self.logger.info("✅ Service container initialized")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Failed to initialize application: {e}")
            else:
                print(f"❌ Failed to initialize application: {e}")
            return False

    def start_services(self) -> None:
        """Start all background services."""
        if not self.container or not self.logger:
            raise RuntimeError("Application not properly initialized")

        # Get camera manager and set shutdown flag
        camera_manager = self.container.get(CameraManager)
        camera_manager.shutdown_flag = self.shutdown_flag

        # Start timelapser thread
        self.logger.info("Starting timelapser orchestrator...")
        orchestrator = self.container.get(TimelapseOrchestratorService)
        self.timelapser_thread = threading.Thread(
            target=orchestrator.run_timelapser,
            args=(self.shutdown_flag,),
            name="TimelapserThread",
            daemon=True,
        )
        self.timelapser_thread.start()
        self.logger.info("✅ Timelapser orchestrator started")

        # Start cleanup thread
        self.logger.info("Starting cleanup worker...")
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker,
            name="CleanupThread",
            daemon=True,
        )
        self.cleanup_thread.start()
        self.logger.info("✅ Cleanup worker started")

        # Start web server thread
        self.logger.info("Starting web dashboard server...")
        self.web_server_thread = threading.Thread(
            target=self._web_server_worker,
            args=(camera_manager,),
            name="WebServerThread",
            daemon=True,
        )
        self.web_server_thread.start()
        self.logger.info("✅ Web dashboard server started")

        # Log current settings
        interval = self.config.get_capture_interval()
        timezone = self.config.get_timezone_str()
        storage_path = self.config.get_storage_path()

        self.logger.info("📋 Current Settings:")
        self.logger.info(f"   Capture interval: {interval} seconds")
        self.logger.info(f"   Timezone: {timezone}")
        self.logger.info(f"   Storage path: {storage_path}")

        self.logger.info("=" * 50)
        self.logger.info("🎬 UniFi Timelapser is running!")
        self.logger.info("   Press Ctrl+C to stop")
        self.logger.info("=" * 50)

    def _cleanup_worker(self) -> None:
        """Simple cleanup worker that runs periodically."""
        self.logger.info("Cleanup worker started")

        # Get cleanup service from container
        cleanup_service = self.container.get(CleanupService)

        while not self.shutdown_flag.is_set():
            try:
                # Run storage cleanup if configured
                self.logger.debug("Running image cleanup cycle")
                cleanup_service.run_purge_cycle()

                # Run log cleanup if configured
                self.logger.debug("Running log cleanup cycle")
                cleanup_service.run_log_cleanup_cycle()

            except Exception as e:
                self.logger.error(f"Error in cleanup worker: {e}", exc_info=True)

            # Sleep for 1 hour between cleanup cycles
            self.shutdown_flag.wait(3600)  # 1 hour

        self.logger.info("Cleanup worker stopped")

    def _web_server_worker(self, camera_manager: CameraManager) -> None:
        """Web server worker that runs the FastAPI dashboard."""
        self.logger.info("Web server worker started")

        try:
            # Create web server instance
            web_server = UniFiTimeLapserWebServer(
                self.config, camera_manager, self.logger
            )

            # Get web dashboard settings
            web_settings = self.config.get_web_dashboard_settings_typed()
            if not web_settings.enabled:
                self.logger.info("Web dashboard is disabled in configuration")
                return

            # Configure uvicorn
            uvicorn_config = uvicorn.Config(
                app=web_server.get_app(),
                host=web_settings.host,
                port=web_settings.port,
                log_level="info",
                access_log=False,  # Disable access logs to reduce noise
                loop="asyncio",
            )

            # Create and run the server
            server = uvicorn.Server(uvicorn_config)

            self.logger.info(
                f"Starting FastAPI web dashboard on {web_settings.host}:{web_settings.port}"
            )
            self.logger.info(
                f"📊 Dashboard: http://{web_settings.host}:{web_settings.port}/"
            )
            self.logger.info(
                f"📖 API Docs: http://{web_settings.host}:{web_settings.port}/api/docs"
            )
            self.logger.info(
                f"🔌 API Health: http://{web_settings.host}:{web_settings.port}/api/health"
            )

            # This will block until the server is shut down
            server.run()

        except Exception as e:
            self.logger.error(f"Error in web server worker: {e}", exc_info=True)
        finally:
            self.logger.info("Web server worker stopped")

    def shutdown(self) -> None:
        """Gracefully shutdown all services."""
        if not self.logger:
            return

        self.logger.info("🛑 Shutting down application...")
        self.shutdown_flag.set()

        # Wait for threads to finish with timeouts
        if self.timelapser_thread and self.timelapser_thread.is_alive():
            self.logger.info("Waiting for timelapser thread to finish...")
            self.timelapser_thread.join(timeout=3)
            if self.timelapser_thread.is_alive():
                self.logger.warning("Timelapser thread didn't stop gracefully")

        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.logger.info("Waiting for cleanup thread to finish...")
            self.cleanup_thread.join(timeout=2)
            if self.cleanup_thread.is_alive():
                self.logger.warning("Cleanup thread didn't stop gracefully")

        if self.web_server_thread and self.web_server_thread.is_alive():
            self.logger.info("Waiting for web server thread to finish...")
            self.web_server_thread.join(timeout=2)
            if self.web_server_thread.is_alive():
                self.logger.warning("Web server thread didn't stop gracefully")

        self.logger.info("✅ Shutdown complete")

    def run_main_loop(self) -> None:
        """Run the main application loop."""
        try:
            while not self.shutdown_flag.is_set():
                # Check shutdown more frequently for faster response
                if self.shutdown_flag.wait(1.0):
                    break

                # Health check: restart timelapser thread if it died
                if int(time.time()) % 30 == 0:
                    if self.timelapser_thread and not self.timelapser_thread.is_alive():
                        self.logger.error("❌ Timelapser thread died, restarting...")
                        orchestrator = self.container.get(TimelapseOrchestratorService)
                        self.timelapser_thread = threading.Thread(
                            target=orchestrator.run_timelapser,
                            args=(self.shutdown_flag,),
                            name="TimelapserThread",
                            daemon=True,
                        )
                        self.timelapser_thread.start()

        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
            self.shutdown_flag.set()


# Global application instance for signal handlers
app_manager: Optional[ApplicationManager] = None


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    if app_manager and app_manager.logger:
        app_manager.logger.info(
            f"🛑 Received signal {signum}, shutting down gracefully..."
        )
    else:
        print(f"🛑 Received signal {signum}, shutting down gracefully...")

    if app_manager:
        app_manager.shutdown_flag.set()


def main() -> NoReturn:
    """Main application entry point."""
    global app_manager

    try:
        # Initialize application manager
        app_manager = ApplicationManager()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Initialize dependencies
        if not app_manager.initialize():
            sys.exit(1)

        # Start all services
        app_manager.start_services()

        # Run main loop
        app_manager.run_main_loop()

        # Shutdown gracefully
        app_manager.shutdown()
        sys.exit(0)

    except Exception as e:
        if app_manager and app_manager.logger:
            app_manager.logger.exception(f"❌ Fatal error in main application: {e}")
        else:
            print(f"❌ Fatal error in main application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
