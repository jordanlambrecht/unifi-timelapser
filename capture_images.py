import os
import subprocess
from datetime import datetime, timedelta
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
import threading
import pytz

# Constants
LOG_DIR = os.getenv('LOG_DIR', '/logs')
LOG_FILE = os.getenv('LOG_FILE', 'unifi_timelapse.log')
CONFIG_RELOAD_INTERVAL = 3600  # 1 hour
HEALTH_CHECK_INTERVAL = 300  # 5 minutes
IMAGE_CAPTURE_RETRIES = 3
IMAGE_CAPTURE_SLEEP = 5
TIMELAPSE_COMPRESS_QUALITY_STEP = 5

# Timezone
TIMEZONE = os.getenv('TZ', 'UTC')
timezone = pytz.timezone(TIMEZONE)

# Initialize global variables and lock
config = {}
config_lock = threading.Lock()
logger = None  # Placeholder for logger

# Flask app for configuration reload
app = Flask(__name__)

@app.route('/reload', methods=['POST'])
def reload_config():
    """Reload configuration from environment variables."""
    with config_lock:
        load_config()
    return 'Configuration reloaded', 200

def health_check():
    """Perform health checks on camera URLs."""
    while True:
        with config_lock:
            camera_urls = config["CAMERA_RTSPS_LIST"]
        
        for camera_url in camera_urls:
            try:
                response = subprocess.run(["ffprobe", camera_url], capture_output=True, text=True, timeout=10)
                if response.returncode != 0:
                    logger.error(f"Health check failed for {camera_url}: {response.stderr}")
                    # Add notification logic here
            except subprocess.TimeoutExpired:
                logger.error(f"Health check timeout for {camera_url}")
                # Add notification logic here
            except Exception as e:
                logger.error(f"Health check exception for {camera_url}: {str(e)}")
                # Add notification logic here
        time.sleep(HEALTH_CHECK_INTERVAL)

def load_config():
    """Load configuration from environment variables."""
    global config
    config = {
        "CAMERA_RTSPS_LIST": [item.strip() for item in os.getenv('CAMERA_RTSPS_LIST', '').split(',')],
        "CAMERA_NAME_LIST": [item.strip() for item in os.getenv('CAMERA_NAME_LIST', '').split(',')],
        "ROTATE_LIST": [item.strip() for item in os.getenv('ROTATE_LIST', 'none').split(',')],
        "OUTPUT_DIR": os.getenv('OUTPUT_DIR', '/media'),
        "IMAGE_TYPE": os.getenv('IMAGE_TYPE', 'png'),
        "FREQUENCY": int(os.getenv('FREQUENCY', '900')),
        "CLEANUP_DAYS": int(os.getenv('CLEANUP_DAYS', '30')),
        "LOG_CLEANUP_DAYS": int(os.getenv('LOG_CLEANUP_DAYS', '30')),
        "TIMELAPSE_ENABLED": os.getenv('TIMELAPSE_ENABLED', 'false').lower() == 'true',
        "CHECKPOINT_ENABLED": os.getenv('CHECKPOINT_ENABLED', 'false').lower() == 'true',
        "MAX_TIMELAPSE_SIZE": int(os.getenv('MAX_TIMELAPSE_SIZE', '0')),
        "TIMELAPSE_FORMAT": os.getenv('TIMELAPSE_FORMAT', 'mp4'),
        "TIMELAPSE_SPEED": int(os.getenv('TIMELAPSE_SPEED', '30')),
        "LOG_LEVEL": os.getenv('LOG_LEVEL', 'INFO').upper(),  # Log level
        "MAX_IMAGE_SIZE": int(os.getenv('MAX_IMAGE_SIZE', '0')),  # Max image size in KB
        "TIME_START": os.getenv('TIME_START', '00:00'),
        "TIME_STOP": os.getenv('TIME_STOP', '00:00')
    }

    # Ensure ROTATE_LIST has the same length as CAMERA_RTSPS_LIST and CAMERA_NAME_LIST
    if len(config['ROTATE_LIST']) != len(config['CAMERA_RTSPS_LIST']):
        config['ROTATE_LIST'] = ['none'] * len(config['CAMERA_RTSPS_LIST'])

    if len(config['CAMERA_NAME_LIST']) != len(config['CAMERA_RTSPS_LIST']):
        raise ValueError("The number of camera names must match the number of camera RTSPS URLs.")
    
    # Convert TIME_START and TIME_STOP to datetime.time objects
    config['TIME_START'] = datetime.strptime(config['TIME_START'], '%H:%M').time()
    config['TIME_STOP'] = datetime.strptime(config['TIME_STOP'], '%H:%M').time()

def setup_logging():
    """Setup logging configuration."""
    global logger
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, LOG_FILE)

    logger = logging.getLogger('UniFiTimelapseLogger')
    logger.setLevel(config['LOG_LEVEL'])

    console_handler = logging.StreamHandler()
    console_handler.setLevel(config['LOG_LEVEL'])
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)

    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
    file_handler.setLevel(config['LOG_LEVEL'])
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Set timezone for logging
    logging.Formatter.converter = lambda *args: datetime.now(tz=timezone).timetuple()

def create_directories():
    """Create necessary directories for storing images and timelapses."""
    for camera_name in config["CAMERA_NAME_LIST"]:
        os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'frames'), exist_ok=True)
        os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'checkpoint_timelapses'), exist_ok=True)
        os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'rolling_timelapses'), exist_ok=True)

def get_rotate_filter(rotate_option):
    """Get the appropriate ffmpeg rotate filter based on the rotate option."""
    if rotate_option == "left":
        return "transpose=2"
    elif rotate_option == "right":
        return "transpose=1"
    elif rotate_option == "invert":  # 180-degree rotation
        return "transpose=2,transpose=2"
    return ""

def capture_image(camera_url, output_dir, prefix, image_type, rotate_option, retries=IMAGE_CAPTURE_RETRIES):
    """Capture an image from a camera URL."""
    timestamp = datetime.now(timezone).strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, 'frames', f"{prefix}_{timestamp}.{image_type}")
    rotate_filter = get_rotate_filter(rotate_option)
    
    for attempt in range(retries):
        try:
            ffmpeg_command = ["ffmpeg", "-y", "-i", camera_url, "-vframes", "1"]
            if rotate_filter:
                ffmpeg_command += ["-vf", rotate_filter]
            ffmpeg_command += [output_path]
            
            result = subprocess.run(ffmpeg_command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(result.stderr)

            # Compress the image if MAX_IMAGE_SIZE is set
            if config["MAX_IMAGE_SIZE"] > 0:
                compress_image(output_path, config["MAX_IMAGE_SIZE"])

            logger.info(f"Saved image to {output_path}")
            return
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error for {prefix} camera: {e.stderr}")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed to capture image for {prefix} camera: {str(e)}")
            time.sleep(IMAGE_CAPTURE_SLEEP)
    logger.error(f"Failed to capture image for {prefix} camera after {retries} attempts")

def compress_image(image_path, max_size_kb):
    """Compress the image to ensure it does not exceed max_size_kb."""
    try:
        file_size_kb = os.path.getsize(image_path) / 1024
        quality = 100
        while file_size_kb > max_size_kb and quality > 10:
            result = subprocess.run(
                ["ffmpeg", "-i", image_path, "-q:v", str(quality), image_path],
                capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(result.stderr)
            file_size_kb = os.path.getsize(image_path) / 1024
            quality -= TIMELAPSE_COMPRESS_QUALITY_STEP
        logger.info(f"Compressed image to {file_size_kb:.2f} KB with quality {quality}")
    except Exception as e:
        logger.error(f"Failed to compress image {image_path}: {str(e)}")

def cleanup_old_images(output_dir, days):
    """Clean up images older than the specified number of days."""
    if days == 0:
        logger.info("Image cleanup is disabled (CLEANUP_DAYS is set to 0). Skipping cleanup.")
        return
    
    cutoff = datetime.now(timezone) - timedelta(days=days)
    for camera_name in config["CAMERA_NAME_LIST"]:
        frames_dir = os.path.join(output_dir, camera_name, 'frames')
        for filename in os.listdir(frames_dir):
            file_path = os.path.join(frames_dir, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path)).replace(tzinfo=timezone)
                if file_time < cutoff:
                    os.remove(file_path)
                    logger.info(f"Deleted old image {file_path}")

def cleanup_logs(log_dir, days):
    """Clean up logs older than the specified number of days."""
    if days == 0:
        logger.info("Log cleanup is disabled (LOG_CLEANUP_DAYS is set to 0). Skipping cleanup.")
        return

    cutoff = datetime.now(timezone) - timedelta(days=days)
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path)).replace(tzinfo=timezone)
            if file_time < cutoff:
                os.remove(file_path)
                logger.info(f"Deleted old log file {file_path}")

def create_timelapse(camera_name, output_dir, frame_rate, rotate_option, checkpoint=False):
    """Create a timelapse video from captured images."""
    timestamp = datetime.now(timezone).strftime("%Y%m%d_%H%M%S")
    frames_dir = os.path.join(output_dir, 'frames')
    if checkpoint:
        output_path = os.path.join(output_dir, 'checkpoint_timelapses', f"{camera_name}_timelapse_{timestamp}.{config['TIMELAPSE_FORMAT']}")
    else:
        output_path = os.path.join(output_dir, 'rolling_timelapses', f"{camera_name}_timelapse.{config['TIMELAPSE_FORMAT']}")

    input_pattern = os.path.join(frames_dir, f"{camera_name}_*.{config['IMAGE_TYPE']}")

    if not os.path.exists(frames_dir) or not any(fname.startswith(f"{camera_name}_") for fname in os.listdir(frames_dir)):
        logger.error(f"No images found for {camera_name}. Skipping timelapse creation.")
        return

    if not checkpoint:
        rolling_timelapses_dir = os.path.join(output_dir, 'rolling_timelapses')
        for filename in os.listdir(rolling_timelapses_dir):
            if filename.startswith(f"{camera_name}_timelapse") and filename.endswith(f".{config['TIMELAPSE_FORMAT']}"):
                os.remove(os.path.join(rolling_timelapses_dir, filename))
                logger.info(f"Deleted old rolling timelapse {filename} for {camera_name}")

    logger.info(f"Creating timelapse video for {camera_name} with frame rate {frame_rate} fps")
    try:
        rotate_filter = get_rotate_filter(rotate_option)
        
        ffmpeg_command = ["ffmpeg", "-y", "-pattern_type", "glob", "-i", input_pattern, "-r", str(frame_rate)]
        if rotate_filter:
            ffmpeg_command += ["-vf", rotate_filter]
        ffmpeg_command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
        
        result = subprocess.run(ffmpeg_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(result.stderr)

        if config["MAX_TIMELAPSE_SIZE"] > 0:
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            if file_size_mb > config["MAX_TIMELAPSE_SIZE"]:
                os.remove(output_path)
                logger.warning(f"Timelapse video for {camera_name} exceeded maximum size of {config['MAX_TIMELAPSE_SIZE']} MB and was deleted.")
            else:
                logger.info(f"Saved timelapse video to {output_path}")
        else:
            logger.info(f"Saved timelapse video to {output_path}")
    except Exception as e:
        logger.error(f"Failed to create timelapse for {camera_name}: {str(e)}")

def run_timelapser():
    """Main loop for capturing images and creating timelapses."""
    while True:
        current_time = datetime.now(timezone).time()

        with config_lock:
            time_start = config['TIME_START']
            time_stop = config['TIME_STOP']
            frequency = config['FREQUENCY']
        
        if time_start == datetime.strptime('00:00', '%H:%M').time() and time_stop == datetime.strptime('00:00', '%H:%M').time():
            within_time_window = True
        elif time_start < time_stop:
            within_time_window = time_start <= current_time <= time_stop
        else:  # Time window spans midnight
            within_time_window = current_time >= time_start or current_time <= time_stop

        if within_time_window:
            with config_lock:
                camera_rtsp_list = config["CAMERA_RTSPS_LIST"]
                camera_name_list = config["CAMERA_NAME_LIST"]
                rotate_list = config["ROTATE_LIST"]
                output_dir = config["OUTPUT_DIR"]
                image_type = config["IMAGE_TYPE"]
                timelapse_enabled = config["TIMELAPSE_ENABLED"]
                timelapse_speed = config["TIMELAPSE_SPEED"]
                cleanup_days = config["CLEANUP_DAYS"]
                log_cleanup_days = config["LOG_CLEANUP_DAYS"]

            for i, camera_url in enumerate(camera_rtsp_list):
                camera_name = camera_name_list[i]
                rotate_option = rotate_list[i]
                try:
                    capture_image(camera_url, os.path.join(output_dir, camera_name), camera_name, image_type, rotate_option)
                except Exception as e:
                    logger.error(f"Failed to capture image for {camera_name} camera: {str(e)}")

            if timelapse_enabled:
                for i, camera_name in enumerate(camera_name_list):
                    rotate_option = rotate_list[i]
                    try:
                        create_timelapse(camera_name, os.path.join(output_dir, camera_name), timelapse_speed, rotate_option)
                    except Exception as e:
                        logger.error(f"Failed to create timelapse for {camera_name}: {str(e)}")

            cleanup_old_images(output_dir, cleanup_days)
            cleanup_logs(LOG_DIR, log_cleanup_days)

        time.sleep(frequency)

def auto_reload_config():
    """Automatically reload the configuration at regular intervals."""
    while True:
        with config_lock:
            load_config()
        logger.info("Configuration reloaded automatically")
        time.sleep(CONFIG_RELOAD_INTERVAL)

# Load initial configuration and setup logging
load_config()
setup_logging()

# Create necessary directories
create_directories()

# Start threads
timelapser_thread = threading.Thread(target=run_timelapser, daemon=True)
timelapser_thread.start()

health_check_thread = threading.Thread(target=health_check, daemon=True)
health_check_thread.start()

auto_reload_thread = threading.Thread(target=auto_reload_config, daemon=True)
auto_reload_thread.start()

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
