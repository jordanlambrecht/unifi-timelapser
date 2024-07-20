import os
import subprocess
from datetime import datetime, timedelta, time
import time as time_module
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
import threading

# Flask app for configuration reload
app = Flask(__name__)

@app.route('/reload', methods=['POST'])
def reload_config():
    global config
    load_config()
    return 'Configuration reloaded', 200

# Function to load configuration from environment variables
def load_config():
    global config
    config = {
        "CAMERA_RTSPS_LIST": [item.strip() for item in os.getenv('CAMERA_RTSPS_LIST', '').split(',')],
        "CAMERA_NAME_LIST": [item.strip() for item in os.getenv('CAMERA_NAME_LIST', '').split(',')],
        "ROTATE_LIST": [item.strip() for item in os.getenv('ROTATE_LIST', 'none').split(',')],
        "OUTPUT_DIR": os.getenv('OUTPUT_DIR', '/images'),
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

# Load configuration initially
load_config()

# Setup logging
log_dir = '/logs'
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'unifi_timelapse.log')

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

# Create directories if they don't exist
for camera_name in config["CAMERA_NAME_LIST"]:
    os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'frames'), exist_ok=True)
    os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'checkpoint_timelapses'), exist_ok=True)
    os.makedirs(os.path.join(config["OUTPUT_DIR"], camera_name, 'rolling_timelapses'), exist_ok=True)

# Function to capture image with retries
def capture_image(camera_url, output_dir, prefix, image_type, rotate_option, retries=3):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, 'frames', f"{prefix}_{timestamp}.{image_type}")
    rotate_filter = ""
    
    if rotate_option == "left":
        rotate_filter = "transpose=2"
    elif rotate_option == "right":
        rotate_filter = "transpose=1"
    elif rotate_option == "invert":  # 180-degree rotation
        rotate_filter = "transpose=2,transpose=2"
    
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
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed to capture image for {prefix} camera: {str(e)}")
            time_module.sleep(5)
    logger.error(f"Failed to capture image for {prefix} camera after {retries} attempts")

def compress_image(image_path, max_size_kb):
    """Compress the image to ensure it does not exceed max_size_kb"""
    try:
        file_size_kb = os.path.getsize(image_path) / 1024
        if file_size_kb > max_size_kb:
            quality = 95
            while file_size_kb > max_size_kb and quality > 10:
                result = subprocess.run(
                    ["ffmpeg", "-i", image_path, "-q:v", str(quality), image_path],
                    capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(result.stderr)
                file_size_kb = os.path.getsize(image_path) / 1024
                quality -= 5
            logger.info(f"Compressed image to {file_size_kb:.2f} KB with quality {quality}")
    except Exception as e:
        logger.error(f"Failed to compress image {image_path}: {str(e)}")
        
def cleanup_old_images(output_dir, days):
    if days == 0:
        logger.info("Image cleanup is disabled (CLEANUP_DAYS is set to 0). Skipping cleanup.")
        return
    
    cutoff = datetime.now() - timedelta(days=days)
    for camera_name in config["CAMERA_NAME_LIST"]:
        frames_dir = os.path.join(output_dir, camera_name, 'frames')
        for filename in os.listdir(frames_dir):
            file_path = os.path.join(frames_dir, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff:
                    os.remove(file_path)
                    logger.info(f"Deleted old image {file_path}")
                
def cleanup_logs(log_dir, days):
    if days == 0:
        logger.info("Log cleanup is disabled (LOG_CLEANUP_DAYS is set to 0). Skipping cleanup.")
        return

    cutoff = datetime.now() - timedelta(days=days)
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_time < cutoff:
                os.remove(file_path)
                logger.info(f"Deleted old log file {file_path}")

def create_timelapse(camera_name, frames_dir, output_dir, frame_rate, checkpoint=False):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if checkpoint:
        output_path = os.path.join(output_dir, 'checkpoint_timelapses', f"{camera_name}_timelapse_{timestamp}.{config['TIMELAPSE_FORMAT']}")
    else:
        output_path = os.path.join(output_dir, 'rolling_timelapses', f"{camera_name}_timelapse.{config['TIMELAPSE_FORMAT']}")

    input_pattern = os.path.join(frames_dir, f"{camera_name}_*.{config['IMAGE_TYPE']}")

    if not any(fname.startswith(f"{camera_name}_") for fname in os.listdir(frames_dir)):
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
        result = subprocess.run(
            ["ffmpeg", "-y", "-pattern_type", "glob", "-i", input_pattern, "-r", str(frame_rate), "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path],
            capture_output=True, text=True)
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
    while True:
        current_time = datetime.now().time()

        if config['TIME_START'] == time.min and config['TIME_STOP'] == time.min:
            within_time_window = True
        elif config['TIME_START'] < config['TIME_STOP']:
            within_time_window = config['TIME_START'] <= current_time <= config['TIME_STOP']
        else:  # Time window spans midnight
            within_time_window = current_time >= config['TIME_START'] or current_time <= config['TIME_STOP']

        if within_time_window:
            for i, camera_url in enumerate(config["CAMERA_RTSPS_LIST"]):
                camera_name = config["CAMERA_NAME_LIST"][i]
                rotate_option = config["ROTATE_LIST"][i]
                try:
                    capture_image(camera_url, os.path.join(config["OUTPUT_DIR"], camera_name), camera_name, config["IMAGE_TYPE"], rotate_option)
                except Exception as e:
                    logger.error(f"Failed to capture image for {camera_name} camera: {str(e)}")

            if config["TIMELAPSE_ENABLED"]:
                for camera_name in config["CAMERA_NAME_LIST"]:
                    try:
                        create_timelapse(camera_name, os.path.join(config["OUTPUT_DIR"], camera_name, "frames"), os.path.join(config["OUTPUT_DIR"], camera_name, "rolling_timelapses"), config["TIMELAPSE_SPEED"])
                    except Exception as e:
                        logger.error(f"Failed to create timelapse for {camera_name}: {str(e)}")

            cleanup_old_images(config["OUTPUT_DIR"], config["CLEANUP_DAYS"])
            cleanup_logs(log_dir, config["LOG_CLEANUP_DAYS"])

        time_module.sleep(config["FREQUENCY"])
        
        
# Run the timelapser in a separate thread
timelapser_thread = threading.Thread(target=run_timelapser)
timelapser_thread.start()

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)