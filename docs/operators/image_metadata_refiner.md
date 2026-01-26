# ImageMetadataRefiner

Extract basic image metadata: dimensions, file size, and format.

## Overview

A lightweight refiner that extracts fundamental image properties. Should be run early in the pipeline as other operators depend on these fields.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_width` | `int32` | Image width in pixels |
| `image_height` | `int32` | Image height in pixels |
| `image_file_size_bytes` | `int64` | File size in bytes |
| `image_format` | `string` | Image format (JPEG, PNG, WEBP, etc.) |

## Parameters

None - this refiner has no configurable parameters.

## Usage

```yaml
stages:
  - name: metadata
    operators:
      - name: image_metadata_refiner
```

## Input Requirements

Expects records with an `image` field containing:
```python
{
    "image": {
        "bytes": b"..."  # Raw image bytes
    }
}
```

## Error Handling

If image decoding fails:
- `image_width`: 0
- `image_height`: 0
- `image_file_size_bytes`: length of bytes (if available)
- `image_format`: "ERROR"

## Performance

- **Throughput**: ~27,000 records/sec
- **Memory**: Minimal (PIL lazy loading)

## Downstream Dependencies

These operators require `ImageMetadataRefiner` output:
- `ImageQualityFilter` - uses width/height for size filtering
- Various refiners that need image dimensions

## Example Output

```python
{
    "image_width": 1920,
    "image_height": 1080,
    "image_file_size_bytes": 245789,
    "image_format": "JPEG"
}
```
