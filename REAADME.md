
UniFi Timelapser
================

Overview
--------
UniFi Timelapser is a Docker-based solution for capturing images from UniFi cameras at regular intervals and creating timelapse videos from these images. This project is configured to use environment variables for flexibility and ease of deployment.

Project Structure
-----------------
The project directory structure is as follows:

unifi-timelapser/
│
├── capture_images.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── unifi-timelapser/
│   ├── media/
│   └── logs/

- capture_images.py: The Python script responsible for capturing images from the cameras, cleaning up old images, and creating timelapse videos.
- Dockerfile: The Dockerfile used to build the Docker image.
- docker-compose.yml: The Docker Compose file used to define and run the Docker container.
- requirements.txt: The file listing the Python dependencies.
- unifi-timelapser/media: Directory where captured images will be stored.
- unifi-timelapser/logs: Directory where log files will be stored.

Prerequisites
-------------
- Docker
- Docker Compose

Setup Instructions
------------------
1. Clone the repository to your local machine.

    git clone <repository-url>
    cd unifi-timelapser

2. Ensure the directory structure is as shown above.

3. Customize the environment variables in the docker-compose.yml file as needed:

    - CAMERA_RTSPS_LIST: Comma-separated list of RTSPS URLs for your UniFi cameras.
    - CAMERA_NAME_LIST: Comma-separated list of names corresponding to the cameras in CAMERA_RTSPS_LIST.
    - OUTPUT_DIR: Directory where images will be saved inside the container (default is /images).
    - IMAGE_TYPE: Type of images to be captured (png or jpg).
    - FREQUENCY: Frequency of image capture in seconds (default is 900 seconds for 15 minutes).
    - CLEANUP_DAYS: Number of days to keep the images. Set to 0 to disable cleanup.
    - TIMELAPSE_ENABLED: Set to true to enable timelapse creation.
    - CHECKPOINT_ENABLED: Set to true to enable daily checkpoint timelapse creation.
    - MAX_TIMELAPSE_SIZE: Maximum file size for timelapse videos in MB. Set to 0 for unlimited.
    - TIMELAPSE_FORMAT: Format for the timelapse video (mp4 or mov).
    - TIMELAPSE_SPEED: Frame rate for the timelapse video (frames per second).

4. Build the Docker image.

    docker-compose build

5. Start the Docker container.

    docker-compose up -d

6. Verify that the container is running and check the logs for any errors.

    docker logs unifi-timelapser -f

Environment Variables
---------------------
- CAMERA_RTSPS_LIST: Comma-separated list of RTSPS URLs for your UniFi cameras. Example: rtsps://192.168.1.88:7441/nVt8yHIghbJ6bYGN?enableSrtp,rtsps://192.168.1.89:7441/anotherStreamId?enableSrtp
- CAMERA_NAME_LIST: Comma-separated list of names corresponding to the cameras in CAMERA_RTSPS_LIST. Example: bullet,g3
- OUTPUT_DIR: Directory where images will be saved inside the container (default is /images).
- IMAGE_TYPE: Type of images to be captured (png or jpg).
- FREQUENCY: Frequency of image capture in seconds (default is 900 seconds for 15 minutes).
- CLEANUP_DAYS: Number of days to keep the images. Set to 0 to disable cleanup.
- TIMELAPSE_ENABLED: Set to true to enable timelapse creation.
- CHECKPOINT_ENABLED: Set to true to enable daily checkpoint timelapse creation.
- MAX_TIMELAPSE_SIZE: Maximum file size for timelapse videos in MB. Set to 0 for unlimited.
- TIMELAPSE_FORMAT: Format for the timelapse video (mp4 or mov).
- TIMELAPSE_SPEED: Frame rate for the timelapse video (frames per second).

Volume Mapping
--------------
- ./unifi-timelapser/media:/images: Maps the media directory on the host to the /images directory in the container.
- ./unifi-timelapser/logs:/logs: Maps the logs directory on the host to the /logs directory in the container.

Log Files
---------
- Log files are stored in the unifi-timelapser/logs directory on the host machine.
- Log rotation is handled within the capture_images.py script, with a maximum of 5 log files, each up to 5MB in size.

Script Overview
---------------
- capture_images.py:
  - Captures images from each camera at the specified frequency.
  - Cleans up old images based on the CLEANUP_DAYS variable.
  - Creates timelapse videos if TIMELAPSE_ENABLED is true.
  - Creates daily checkpoint timelapse videos if CHECKPOINT_ENABLED is true.
  - Handles errors and logs activities to both stdout and log files.

Creating Timelapse Videos
-------------------------
- Timelapse videos are created using ffmpeg.
- The frame rate for the timelapse video is controlled by the TIMELAPSE_SPEED variable.
- The format for the timelapse video is specified by the TIMELAPSE_FORMAT variable (mp4 or mov).

