# Video Exact Stream-Level Deduplicator

Deduplicates video records based on raw stream hash (content-level comparison).

## Overview

The `VideoExactStreamLevelDeduplicator` uses FFmpeg to extract raw video frames and compute a hash, ignoring container metadata. This allows detecting duplicates even when videos have different containers (e.g., MP4 vs MKV) or metadata.

**Key characteristics:**
- Container-agnostic deduplication
- Detects duplicates regardless of container format or metadata
- Requires FFmpeg to be installed
- Extends `VideoDeduplicator` base class for video loading

## Requirements

- **FFmpeg** must be installed and available in PATH

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Check installation
ffmpeg -version
```

## Usage

### YAML Configuration

```yaml
operators:
  - name: video_exact_stream_level_deduplicator
    params:
      video_path_field: "video_path"
      hash_algorithm: "md5"
      include_audio: false
```

### Python API

```python
from mega_data_factory.operators.dedup import VideoExactStreamLevelDeduplicator

dedup = VideoExactStreamLevelDeduplicator(
    video_path_field="video_path",
    include_audio=True,
)

# Get dedup keys for records
keys = dedup.get_dedup_keys_batch(records)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `video_field` | str | "video" | Field name for video data (dict with "path" key) |
| `video_url_field` | str | "video_url" | Field name for video URL |
| `video_path_field` | str | "video_path" | Field name for video file path |
| `hash_algorithm` | str | "md5" | Hash algorithm: "md5", "sha256" |
| `include_audio` | bool | False | Whether to include audio stream in hash |
| `cache_dir` | str | None | Directory to cache downloaded videos |
| `download_timeout` | int | 120 | Timeout in seconds for downloading videos |
| `max_file_size` | int | None | Maximum file size in bytes to process |

## How It Works

```
┌─────────────┐     ┌─────────┐     ┌──────────────┐     ┌──────┐
│ Video File  │────▶│ FFmpeg  │────▶│ Raw Frames   │────▶│ Hash │
│ (any format)│     │ Decode  │     │ (rgb24)      │     │      │
└─────────────┘     └─────────┘     └──────────────┘     └──────┘
```

1. FFmpeg decodes the video to raw RGB24 frames
2. Raw frame data is streamed to the hash function
3. Container metadata and encoding details are ignored
4. Only the actual visual content is compared

## Input Formats

The deduplicator supports file paths and URLs only (not in-memory bytes for memory efficiency):

### 1. Local File Path

```python
record = {
    "id": "video_001",
    "video_path": "/path/to/video.mp4"
}
```

### 2. Remote URL (downloaded and cached)

```python
record = {
    "id": "video_001",
    "video_url": "https://example.com/video.mp4"
}
```

## What Gets Detected as Duplicates

| Scenario | Detected? |
|----------|-----------|
| Same file, different filename | ✅ Yes |
| Same content, different container (MP4 vs MKV) | ✅ Yes |
| Same content, different metadata | ✅ Yes |
| Same content, re-encoded (lossless) | ✅ Yes |
| Same content, re-encoded (lossy) | ❌ No |
| Same content, different resolution | ❌ No |
| Same content, different frame rate | ❌ No |

## Pre-computed Hashes

If records already have a stream hash field, it will be used directly:

```python
record = {
    "id": "video_001",
    "video_stream_hash": "abc123...",  # Will use this instead of computing
}
```

Supported fields: `video_stream_hash`, `stream_hash`

## Architecture

The `VideoExactStreamLevelDeduplicator` extends `VideoDeduplicator` base class:

```
VideoDeduplicator (base)
├── Handles video loading (file paths, URLs)
├── Manages caching and downloading
├── Implements get_dedup_keys_batch()
├── Provides cleanup_batch() for resource cleanup
└── Calls abstract compute_hash() method

VideoExactStreamLevelDeduplicator (subclass)
└── Implements compute_hash() using FFmpeg stream extraction
```

## Batch Cleanup

Downloaded video files are automatically cleaned up by the `RayWorker` after each batch is processed (after all operators in a stage have finished). This ensures:

1. Temporary files don't accumulate during processing
2. All operators in a stage can access the downloaded files
3. Disk space is freed after each batch

The cleanup is handled at the worker level, not within individual operators, so multiple operators can share downloaded video files within the same batch.

## Performance

- **Speed**: Slower than byte-level (requires video decoding)
- **Memory**: Streaming processing, moderate memory usage
- **CPU**: Higher CPU usage due to video decoding

### Optimization Tips

1. Use `md5` instead of `sha256` for faster hashing
2. Set `include_audio=False` if audio doesn't matter
3. Use `max_file_size` to skip very large files
4. Pre-compute hashes and store in `video_stream_hash` field

## Example

```python
from mega_data_factory.operators.dedup import VideoExactStreamLevelDeduplicator

# Initialize deduplicator
dedup = VideoExactStreamLevelDeduplicator(
    video_path_field="video_path",
    hash_algorithm="md5",
    include_audio=False,
    max_file_size=500 * 1024 * 1024,  # 500MB limit
)

# Process records
records = [
    {"id": "1", "video_path": "/videos/video1.mp4"},
    {"id": "2", "video_path": "/videos/video1.mkv"},  # Same content, different container
    {"id": "3", "video_path": "/videos/video2.mp4"},  # Different content
]

keys = dedup.get_dedup_keys_batch(records)
# keys[0] == keys[1] (same content, different container)
# keys[0] != keys[2] (different content)
```

## Comparison with Byte-Level Deduplication

| Feature | Byte-Level | Stream-Level |
|---------|------------|--------------|
| Speed | Fast | Slower |
| Container-agnostic | ❌ | ✅ |
| Metadata-agnostic | ❌ | ✅ |
| Dependencies | None | FFmpeg |
| Memory usage | Low | Moderate |

## See Also

- [`VideoExactByteLevelDeduplicator`](video_exact_byte_level_dedup.md) - Fast byte-level deduplication
- [`VideoDeduplicator`](video_deduplicator.py) - Base class for video deduplication
- [`ImagePhashDeduplicator`](image_phash_dedup.md) - Perceptual hash for images
