"""
Parquet Data Writer

Writes data to Parquet files with incremental writes using PyArrow and fsspec.
Supports both local filesystem and cloud storage (S3, GCS, etc.).
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import fsspec
import pyarrow as pa
import pyarrow.parquet as pq

from mega_data_factory.framework import DataWriter


class ParquetDataWriter(DataWriter):
    """DataWriter that writes to Parquet files using PyArrow and fsspec.

    Supports both local filesystem and cloud storage (S3, GCS, etc.).
    """

    def __init__(
        self,
        output_path: str,
        table_name: str = "default",
        partition_by: str | None = None,
        partition_key_extractor: str | None = None,
    ):
        """Initialize Parquet writer.

        Args:
            output_path: Directory path for output files (local or cloud, e.g., 's3://bucket/path')
            table_name: Name of the table/subdirectory
            partition_by: Column name to partition by (e.g., 'operator' for rejected samples)
            partition_key_extractor: JSON path to extract partition key from a nested field
                                    (e.g., '_rejection_details.operator' extracts operator from
                                    the _rejection_details dict/JSON field)
        """
        self.output_path = output_path.rstrip("/")
        self.table_name = table_name
        self.partition_by = partition_by
        self.partition_key_extractor = partition_key_extractor

        # Get filesystem from path (auto-detects local, s3://, gs://, etc.)
        self.fs, self.root_path = fsspec.core.url_to_fs(self.output_path)

        # Full output directory including table name
        self.full_output_path = f"{self.root_path}/{self.table_name}"

        # Ensure output directory exists
        self.fs.makedirs(self.full_output_path, exist_ok=True)

    def _extract_partition_key(self, record: dict[str, Any]) -> str:
        """Extract partition key from a record.

        Args:
            record: The record to extract partition key from

        Returns:
            The partition key value, or 'unknown' if not found
        """
        if not self.partition_by:
            return "default"

        # If partition_key_extractor is set, use it to extract from nested field
        if self.partition_key_extractor:
            parts = self.partition_key_extractor.split(".")
            value = record
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, str):
                    # Try to parse as JSON
                    try:
                        value = json.loads(value)
                        value = value.get(part)
                    except (json.JSONDecodeError, AttributeError):
                        return "unknown"
                else:
                    return "unknown"
                if value is None:
                    return "unknown"
            return str(value) if value else "unknown"

        # Direct column access
        value = record.get(self.partition_by)
        if value is None:
            return "unknown"
        return str(value)

    def write(self, data: list[dict[str, Any]]):
        """Write data to Parquet files using PyArrow (fast, no pandas conversion).

        If partition_by is set, data will be partitioned into subdirectories.

        Args:
            data: List of processed records to write
        """
        if not data:
            return

        # If partitioning is enabled, group data by partition key
        if self.partition_by:
            partitions: dict[str, list[dict[str, Any]]] = {}
            for record in data:
                partition_key = self._extract_partition_key(record)
                # Sanitize partition key for filesystem (replace special chars)
                safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in partition_key)
                if safe_key not in partitions:
                    partitions[safe_key] = []
                partitions[safe_key].append(record)

            # Write each partition separately
            for partition_key, partition_data in partitions.items():
                self._write_partition(partition_data, partition_key)
        else:
            # No partitioning, write all data to single directory
            self._write_partition(data, None)

    def _write_partition(self, data: list[dict[str, Any]], partition_key: str | None):
        """Write data to a specific partition.

        Args:
            data: List of records to write
            partition_key: Partition key (subdirectory name), or None for no partitioning
        """
        if not data:
            return

        # Convert directly to PyArrow Table (no pandas overhead)
        arrow_table = pa.Table.from_pylist(data)

        # Determine output path
        if partition_key:
            partition_path = f"{self.full_output_path}/{self.partition_by}={partition_key}"
            self.fs.makedirs(partition_path, exist_ok=True)
        else:
            partition_path = self.full_output_path

        # Generate unique filename with timestamp and UUID to avoid collisions
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"part_{timestamp}_{unique_id}.parquet"
        parquet_path = f"{partition_path}/{filename}"

        # Write with compression and optimized settings using fsspec
        with self.fs.open(parquet_path, "wb") as f:
            pq.write_table(
                arrow_table,
                f,
                compression="snappy",  # Fast compression
                row_group_size=50000,  # Larger row groups for better performance
                use_dictionary=True,  # Dictionary encoding for better compression
            )

    def close(self):
        """Close writer (no-op for Parquet)."""
        pass
