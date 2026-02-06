# Video Metadata Refiner

## Overview

The `VideoMetadataRefiner` extracts comprehensive video metadata using FFprobe (part of FFmpeg) and enriches records with detailed information about video files. This includes format information, video stream details, audio stream details, and container metadata.

## Features

- **Comprehensive Metadata Extraction**: Extracts format, video, and audio stream information
- **JSON Metadata Field**: Full metadata stored as JSON for flexible querying
- **Extracted Columns**: Common fields extracted as separate columns for easy filtering
- **Video Loading**: Supports URLs and local file paths with automatic caching
- **Batch Cleanup**: Automatic cleanup of downloaded videos after processing

## Requirements

- **FFmpeg/FFprobe**: Must be installed and available in PATH
  ```bash
  # Ubuntu/Debian
  sudo apt-get install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  # Download from https://ffmpeg.org/download.html
  ```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `video_field` | str | "video" | Field name for video data (dict with bytes/path, or direct path) |
| `video_url_field` | str | "video_url" | Field name for video URL |
| `video_path_field` | str | "video_path" | Field name for video file path |
| `cache_dir` | str | None | Directory to cache downloaded videos (default: system temp) |
| `timeout` | int | 60 | Download timeout in seconds |
| `max_file_size` | int | None | Maximum file size in bytes to download |
| `persistent_cache` | bool | False | Keep downloaded files across batches |
| `include_full_metadata` | bool | True | Include full JSON metadata field |

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `video_metadata` | string (JSON) | Full metadata as JSON string (if `include_full_metadata=True`) |
| `video_duration` | float | Duration in seconds |
| `video_width` | int | Video width in pixels |
| `video_height` | int | Video height in pixels |
| `video_fps` | float | Frames per second |
| `video_codec` | string | Video codec name (e.g., "h264", "vp9") |
| `video_bitrate` | int | Video bitrate in bits/second |
| `audio_codec` | string | Audio codec name (e.g., "aac", "mp3") |
| `audio_sample_rate` | int | Audio sample rate in Hz |
| `audio_channels` | int | Number of audio channels |

## Full Metadata Structure

The `video_metadata` JSON field contains the following structure:

```json
{
  "format": {
    "filename": "video.mp4",
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "format_long_name": "QuickTime / MOV",
    "duration": 120.5,
    "size": 15728640,
    "bit_rate": 1048576,
    "nb_streams": 2,
    "nb_programs": 0,
    "start_time": 0.0,
    "tags": {
      "major_brand": "isom",
      "minor_version": "512",
      "compatible_brands": "isomiso2avc1mp41",
      "encoder": "Lavf58.29.100"
    }
  },
  "streams": [
    {
      "index": 0,
      "codec_type": "video",
      "codec_name": "h264",
      "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
      "profile": "High",
      "width": 1920,
      "height": 1080,
      "pix_fmt": "yuv420p",
      "fps": 29.97,
      "r_frame_rate": "30000/1001",
      "avg_frame_rate": "30000/1001",
      "display_aspect_ratio": "16:9",
      "bit_rate": 1000000,
      "duration": 120.5,
      "nb_frames": 3612,
      "color_space": "bt709",
      "color_transfer": "bt709",
      "color_primaries": "bt709"
    },
    {
      "index": 1,
      "codec_type": "audio",
      "codec_name": "aac",
      "codec_long_name": "AAC (Advanced Audio Coding)",
      "profile": "LC",
      "sample_rate": 48000,
      "channels": 2,
      "channel_layout": "stereo",
      "bit_rate": 128000,
      "duration": 120.5
    }
  ],
  "video": { /* Primary video stream info */ },
  "audio": { /* Primary audio stream info */ }
}
```

## Usage Examples

### Basic Usage

```yaml
pipeline:
  stages:
    - name: extract_metadata
      operators:
        - type: VideoMetadataRefiner
```

### With Custom Configuration

```yaml
pipeline:
  stages:
    - name: extract_metadata
      operators:
        - type: VideoMetadataRefiner
          video_url_field: video_url
          cache_dir: /tmp/video_cache
          timeout: 120
          max_file_size: 1073741824  # 1GB limit
          include_full_metadata: true
```

### Without Full Metadata (Smaller Output)

```yaml
pipeline:
  stages:
    - name: extract_metadata
      operators:
        - type: VideoMetadataRefiner
          include_full_metadata: false  # Only extract individual fields
```

### Python API

```python
from mega_data_factory.operators.refiners.video_metadata import VideoMetadataRefiner

# Create refiner
refiner = VideoMetadataRefiner(
    video_url_field="video_url",
    timeout=120,
    include_full_metadata=True,
)

# Process records
records = [
    {"video_url": "https://example.com/video1.mp4"},
    {"video_url": "https://example.com/video2.mp4"},
]

refiner.refine_batch(records)

# Access extracted metadata
for record in records:
    print(f"Duration: {record['video_duration']}s")
    print(f"Resolution: {record['video_width']}x{record['video_height']}")
    print(f"FPS: {record['video_fps']}")
    print(f"Video Codec: {record['video_codec']}")
    print(f"Audio Codec: {record['audio_codec']}")

# Clean up downloaded videos
refiner.cleanup_batch()
```

## Use Cases

### 1. Video Quality Filtering

Filter videos based on resolution, duration, or codec:

```yaml
pipeline:
  stages:
    - name: extract_metadata
      operators:
        - type: VideoMetadataRefiner

    - name: filter_quality
      operators:
        - type: CustomFilter
          condition: "video_width >= 1920 and video_height >= 1080"
```

### 2. Video Format Analysis

Analyze video formats in a dataset:

```python
import json
import pandas as pd

# After processing with VideoMetadataRefiner
df = pd.DataFrame(records)

# Analyze codec distribution
print(df['video_codec'].value_counts())

# Analyze resolution distribution
df['resolution'] = df['video_width'].astype(str) + 'x' + df['video_height'].astype(str)
print(df['resolution'].value_counts())

# Analyze duration distribution
print(df['video_duration'].describe())
```

### 3. Video Transcoding Preparation

Use metadata to determine transcoding requirements:

```python
for record in records:
    metadata = json.loads(record['video_metadata'])

    # Check if transcoding is needed
    needs_transcode = (
        record['video_codec'] not in ['h264', 'h265'] or
        record['video_width'] > 1920 or
        record['video_fps'] > 30
    )

    if needs_transcode:
        # Queue for transcoding
        pass
```

## Performance Considerations

1. **FFprobe Overhead**: Each video requires a subprocess call to FFprobe
2. **Download Time**: Remote videos need to be downloaded before metadata extraction
3. **Disk Space**: Downloaded videos are cached temporarily; use `cleanup_batch()` to free space
4. **Batch Size**: Consider smaller batch sizes for large videos to manage memory

## Error Handling

- Videos that fail to load return `None` for all metadata fields
- FFprobe errors are logged as warnings
- Missing streams (e.g., audio-only files) have `None` for missing stream fields

## Related Operators

- [`VideoExactByteLevelDeduplicator`](../dedup/video_exact_byte_level_dedup.md) - Deduplicate by file hash
- [`VideoExactStreamLevelDeduplicator`](../dedup/video_exact_stream_level_dedup.md) - Deduplicate by stream content
- [`ImageMetadataRefiner`](image_metadata.md) - Similar metadata extraction for images
