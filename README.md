# UniFi Timelapser

## 🚀 Overview

UniFi Timelapser is a modern, Python-based application for capturing images from
UniFi cameras at regular intervals and creating automated timelapse videos.
Built with FastAPI, it features a responsive web dashboard, efficient resource
management, and flexible timelapse generation strategies.

### ✨ Key Features

- **🎬 Smart Timelapse Generation**: Multiple generation modes (every capture,
  periodic, manual-only)
- **📱 Modern Web Dashboard**: Responsive Tailwind CSS interface with real-time
  camera status
- **⚡ Efficient Processing**: Concurrent image capture and intelligent resource
  management
- **🧹 Automatic Cleanup**: Configurable retention policies for images and
  timelapses
- **📊 Real-time Monitoring**: Live camera status, frame counts, and timelapse
  information
- **🔧 Flexible Configuration**: YAML-based config with environment variable
  overrides

## 📋 Configuration

The application uses `config.yaml` for configuration. Here are the key settings:

### 🎬 Timelapse Settings

```yaml
timelapse_settings:
  timelapse_enabled: true # Enable/disable timelapse generation
  checkpoint_enabled: true # Enable daily checkpoint timelapses
  timelapse_generation_frequency: 3600 # Generate timelapses every N seconds (1 hour default)
  timelapse_generation_mode: "periodic" # Generation mode: "every_capture", "periodic", "manual_only"
  continuous_timelapse_max_age_hours: 24 # Keep continuous timelapses for N hours (0 = unlimited)
  max_timelapse_size: 0 # Max timelapse file size in MB (0 = unlimited)
  timelapse_format: "mp4" # Video format (mp4, mov, webm)
  timelapse_speed: 30 # Frame rate in fps
```

#### Timelapse Generation Modes

- **`every_capture`**: Generate timelapse after every image capture cycle (high
  resource usage)
- **`periodic`**: Generate timelapses at configured intervals (recommended for
  efficiency)
- **`manual_only`**: Disable automatic generation (manual triggers only)

### 📷 Camera Settings

```yaml
cameras:
  - name: "bullet"
    url: "rtsp://camera-url"
    enabled: true
    rotation: "left" # none, left, right, invert
```

### ⚙️ Other Settings

- **Image Settings**: Format, compression, capture retries
- **Storage Settings**: Output directories, cleanup policies
- **Operational Settings**: Capture frequency, time windows, timezone
- **Web Dashboard**: Host, port configuration

## 🌳 Environment Variables

For Docker deployments or environment-specific overrides:

- `CAMERA_RTSPS_LIST`: Comma-separated RTSP URLs
- `CAMERA_NAME_LIST`: Corresponding camera names
- `TIMELAPSE_GENERATION_FREQUENCY`: Override generation frequency
- `TIMELAPSE_GENERATION_MODE`: Override generation mode
- `CONTINUOUS_TIMELAPSE_MAX_AGE_HOURS`: Override cleanup policy
- `OUTPUT_DIR`: Storage directory (default: /media)
- `FREQUENCY`: Image capture frequency in seconds
- `TIMEZONE`: Timezone for operations

## 🗺️ Volume Mapping

```yaml
volumes:
  - ./media:/media # Media storage
  - ./logs:/logs # Application logs
  - ./config.yaml:/app/config.yaml # Configuration file
```

## 🚀 Getting Started

### Quick Start with Docker

1. Create your `config.yaml` (see configuration section above)
2. Run with Docker Compose:

```bash
docker-compose up -d
```

### Running Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure cameras in `config.yaml`

3. Start the application:

```bash
python src/main.py
```

4. Access the web dashboard at `http://localhost:9090`

## 📊 Web Dashboard

The modern web interface provides:

- **📱 Responsive Design**: Works on desktop, tablet, and mobile
- **📈 Real-time Status**: Live camera health, capture counts, and error
  monitoring
- **🎬 Timelapse Management**: View latest timelapses, download videos
- **📋 Frame Browser**: Browse captured images with thumbnail previews
- **⚙️ Configuration Display**: Current settings and operational status

### Dashboard Features

- **Camera Cards**: Status indicators, capture statistics, latest timelapse info
- **Frame Tables**: Sortable tables with thumbnails, file sizes, and actions
- **Download Links**: Direct access to images and timelapse videos
- **Error Monitoring**: Visual indicators for camera health issues

## 📼 Timelapse Generation Strategy

### Recommended Configuration

For optimal performance and resource usage:

```yaml
timelapse_settings:
  timelapse_generation_mode: "periodic"
  timelapse_generation_frequency: 3600 # 1 hour
  continuous_timelapse_max_age_hours: 24 # Keep 24 hours of continuous timelapses
```

This configuration:

- ✅ Reduces CPU/disk usage by generating timelapses hourly instead of every
  capture
- ✅ Maintains recent continuous timelapses for immediate viewing
- ✅ Automatically cleans up old files to prevent disk bloat
- ✅ Provides good balance between resource efficiency and content availability

### Generation Modes Comparison

| Mode            | Resource Usage | Use Case                  | Pros                    | Cons                     |
| --------------- | -------------- | ------------------------- | ----------------------- | ------------------------ |
| `every_capture` | High           | Real-time monitoring      | Always current          | CPU/disk intensive       |
| `periodic`      | Low            | General use (recommended) | Efficient, configurable | Slight delay             |
| `manual_only`   | Minimal        | Custom workflows          | Full control            | Requires manual triggers |

## 🧹 Automatic Cleanup

The application includes intelligent cleanup features:

- **Image Cleanup**: Removes old captured images based on `cleanup_days`
- **Continuous Timelapse Cleanup**: Removes continuous timelapses older than
  `continuous_timelapse_max_age_hours`
- **Log Cleanup**: Rotates application logs based on `log_cleanup_days`
- **Checkpoint Preservation**: Daily checkpoint timelapses are preserved longer

## 🔧 Advanced Configuration

### Custom Timelapse Settings

```yaml
timelapse_settings:
  timelapse_width: 1920 # Custom video width
  timelapse_height: 1080 # Custom video height
  timelapse_max_images: 1000 # Limit frames per timelapse
  delete_images_after_timelapse: false # Preserve source images
```

### Performance Tuning

```yaml
image_settings:
  image_capture_retries: 3 # Retry failed captures
  image_capture_sleep: 5 # Delay between retries
  max_image_size: 500 # Compress large images (KB)

operational_settings:
  frequency: 300 # Capture every 5 minutes
  time_start: "06:00" # Start at 6 AM
  time_stop: "22:00" # Stop at 10 PM
```

## 🐞 Troubleshooting

### Common Issues

**Timelapses not generating**: Check generation mode and frequency settings
**High disk usage**: Enable cleanup and reduce retention periods  
**Camera offline**: Verify RTSP URLs and network connectivity **Permission
errors**: Ensure proper volume mount permissions

### Monitoring

- Check logs: `tail -f logs/unifi_timelapser.log`
- Web dashboard: Health indicators and error counts
- API health endpoint: `http://localhost:9090/api/health`

## 📈 Performance Considerations

- **Periodic Mode**: Recommended for production (1-hour intervals)
- **Concurrent Capture**: Multiple cameras captured simultaneously
- **Resource Monitoring**: Built-in health checks and error tracking
- **Efficient Storage**: Automatic cleanup and compression options

---

**Need help?** Check the logs, review configuration, or open an issue for
support.
