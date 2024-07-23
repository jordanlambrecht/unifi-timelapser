
# UniFi Timelapser
================

## 🚀  Overview

UniFi Timelapser is a Docker-based python container for capturing images from UniFi cameras at regular intervals and automating the creation of timelapse videos from these images.


## 🌳  Environment Variables


    - TZ: Duh.
    - CAMERA_RTSPS_LIST: Comma-separated list of RTSPS URLs for your UniFi cameras.
    - CAMERA_NAME_LIST: Comma-separated list of names corresponding to the cameras in CAMERA_RTSPS_LIST.
    - ROTATION_LIST: Accepts NONE, LEFT, RIGHT, INVERT. *Must* be in the same order as the RTSPS list
    - OUTPUT_DIR: Directory where images will be saved inside the container (default is /media).
    - IMAGE_TYPE: Type of images to be captured. Accepts `png` or `jpg`
    - FREQUENCY: Frequency of image capture in seconds (default is 900 seconds for 15 minutes).
    - CLEANUP_DAYS: Number of days to keep the images. Set to 0 to disable cleanup.
    - TIMELAPSE_ENABLED: Set to true to enable timelapse creation.
    - CHECKPOINT_ENABLED: Set to true to enable daily checkpoint timelapse creation at 23:59.
    - MAX_TIMELAPSE_SIZE: Maximum file size for timelapse videos in MB. Set to 0 for unlimited.
    - MAX_IMAGE_SIZE:  Max image size in KB (0 for no compression).
    - TIMELAPSE_FORMAT: Format for the timelapse video (mp4 or mov).
    - TIMELAPSE_SPEED: Frame rate for the timelapse video (frames per second).
    - TIME_START: Daily time to begin taking timelapses. Set this and TIME_STOP to both 0:00 for 24/7.
    - TIME_STOP: Daily time to stop taking timelapses.
    - LOG_LEVEL: Options are DEBUG, INFO, WARNING, ERROR, CRITICAL.
    - LOG_CLEANUP_DAYS: Number of days before it will start to delete log files.


## 🗺️  Volume Mapping

- ./unifi-timelapser/media:/media: Maps the media directory on the host to the /media directory in the container.
- ./unifi-timelapser/logs:/logs: Maps the logs directory on the host to the /logs directory in the container.


## 📼  Creating Timelapse Videos

- Timelapse videos are created using ffmpeg.
- The frame rate for the timelapse video is controlled by the TIMELAPSE_SPEED variable.
- The format for the timelapse video is specified by the TIMELAPSE_FORMAT variable (mp4 or mov).

## 🐞  Known Issues

- Image rotation is currently broken
- Timelapse checkpoints is currently broken