# Video Exact Byte-Level Deduplicator

Deduplicates video records based on exact file hash (byte-level comparison).

## Overview

The `VideoExactByteLevelDeduplicator` uses cryptographic hashing (SHA-256 or MD5) of the entire video file to identify exact duplicates. This is a byte-level comparison that considers the entire file including container metadata.

**Key characteristics:**
- Two videos are duplicates only if they are byte-for-byte identical
- Videos with same content but different containers/encodings are NOT detected
- Fast and reliable for exact duplicate detection
- Extends `VideoDeduplicator` base class for video loading

## Usage

### YAML Configuration

```yaml
operators:
  - name: video_exact_byte_level_deduplicator
    params:
      video_path_field: "video_path"
      hash_algorithm: "sha256"
```

### Python API

```python
from mega_data_factory.operators.dedup import VideoExactByteLevelDeduplicator

dedup = VideoExactByteLevelDeduplicator(
    video_path_field="video_path",
    hash_algorithm="sha256",
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
| `hash_algorithm` | str | "sha256" | Hash algorithm: "sha256", "md5", "sha512" |
| `cache_dir` | str | None | Directory to cache downloaded videos |
| `download_timeout` | int | 60 | Timeout in seconds for downloading videos |
| `max_file_size` | int | None | Maximum file size in bytes to process |

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

### 3. Video Field with Path

```python
record = {
    "id": "video_001",
    "video": {"path": "/path/to/video.mp4"}
}
```

## What Gets Detected as Duplicates

| Scenario | Detected? |
|----------|-----------|
| Same file, different filename | ✅ Yes |
| Same file, different location | ✅ Yes |
| Same content, different container (MP4 vs MKV) | ❌ No |
| Same content, different metadata | ❌ No |
| Same content, re-encoded | ❌ No |

For container-agnostic deduplication, use `VideoExactStreamLevelDeduplicator`.

## Pre-computed Hashes

If records already have a hash field, it will be used directly:

```python
record = {
    "id": "video_001",
    "video_hash": "abc123...",  # Will use this instead of computing
}
```

Supported fields: `video_hash`, `file_hash`

## Architecture

The `VideoExactByteLevelDeduplicator` extends `VideoDeduplicator` base class:

```
VideoDeduplicator (base)
├── Handles video loading (file paths, URLs)
├── Manages caching and downloading
├── Implements get_dedup_keys_batch()
├── Provides cleanup_batch() for resource cleanup
└── Calls abstract compute_hash() method

VideoExactByteLevelDeduplicator (subclass)
└── Implements compute_hash() using file hash
```

## Batch Cleanup

Downloaded video files are automatically cleaned up by the `StageActor` after each batch is processed (after all operators in a stage have finished). This ensures:

1. Temporary files don't accumulate during processing
2. All operators in a stage can access the downloaded files
3. Disk space is freed after each batch

The cleanup is handled at the worker level, not within individual operators, so multiple operators can share downloaded video files within the same batch.

## Performance

- **Speed**: Very fast - only reads file bytes once
- **Memory**: Streaming hash computation, low memory usage
- **I/O**: Single pass through file

## Example

```python
from mega_data_factory.operators.dedup import VideoExactByteLevelDeduplicator

# Initialize deduplicator
dedup = VideoExactByteLevelDeduplicator(
    video_path_field="video_path",
    hash_algorithm="sha256",
    max_file_size=100 * 1024 * 1024,  # 100MB limit
)

# Process records
records = [
    {"id": "1", "video_path": "/videos/video1.mp4"},
    {"id": "2", "video_path": "/videos/video2.mp4"},
    {"id": "3", "video_path": "/videos/video1_copy.mp4"},  # Duplicate of video1
]

keys = dedup.get_dedup_keys_batch(records)
# keys[0] == keys[2] (same file content)
# keys[0] != keys[1] (different files)
```

## See Also

- [`VideoExactStreamLevelDeduplicator`](video_exact_stream_level_dedup.md) - Container-agnostic deduplication
- [`VideoDeduplicator`](video_deduplicator.py) - Base class for video deduplication
- [`ImagePhashDeduplicator`](image_phash_dedup.md) - Perceptual hash for images
