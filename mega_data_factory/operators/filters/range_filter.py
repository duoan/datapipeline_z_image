"""
Range Filter

Filters records based on numeric value range for a given column.
Supports open-ended ranges (min or max can be None to indicate no bound).

Usage:
    # Filter records where score is between 5.0 and 10.0
    filter = RangeFilter(field="score", min_value=5.0, max_value=10.0)

    # Filter records where score >= 5.0 (no upper bound)
    filter = RangeFilter(field="score", min_value=5.0)

    # Filter records where score <= 8.0 (no lower bound)
    filter = RangeFilter(field="score", max_value=8.0)
"""

from typing import Any

from mega_data_factory.framework import Filter
from mega_data_factory.framework.operator import BatchResult


class RangeFilter(Filter):
    """Filter records based on numeric value range for a given column.

    Supports open-ended ranges where min_value or max_value can be None
    to indicate no bound on that side.

    The filter checks if the value in the specified field falls within
    the range [min_value, max_value] (inclusive on both ends).

    Records with missing or non-numeric values in the field are rejected
    by default (configurable via keep_missing parameter).

    The operator name in metrics will include the field name for clarity,
    e.g., "video_aesthetic_score_range_filter" instead of just "range_filter".
    """

    def __init__(
        self,
        field: str,
        min_value: float | int | None = None,
        max_value: float | int | None = None,
        keep_missing: bool = False,
    ):
        """Initialize range filter.

        Args:
            field: Name of the field to filter on.
            min_value: Minimum value (inclusive). None means no lower bound.
            max_value: Maximum value (inclusive). None means no upper bound.
            keep_missing: If True, keep records where the field is missing or non-numeric.
                          If False (default), reject such records.
        """
        super().__init__()

        if min_value is None and max_value is None:
            raise ValueError("At least one of min_value or max_value must be specified")

        self.field = field
        self.min_value = min_value
        self.max_value = max_value
        self.keep_missing = keep_missing

        # Set a descriptive name that includes the field for metrics reporting
        # This overrides the default class name in metrics and rejection details
        self._operator_name = f"{field}_range_filter"

    def _get_numeric_value(self, record: dict[str, Any]) -> float | None:
        """Extract numeric value from record field.

        Returns:
            Float value if field exists and is numeric, None otherwise.
        """
        value = record.get(self.field)
        if value is None:
            return None

        # Handle numeric types
        if isinstance(value, (int, float)):
            return float(value)

        # Try to convert string to float
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None

        return None

    def _is_in_range(self, value: float) -> bool:
        """Check if value is within the specified range."""
        if self.min_value is not None and value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False
        return True

    def _get_rejection_reason(self, value: float | None) -> str:
        """Get a descriptive rejection reason."""
        if value is None:
            return f"missing_or_invalid_{self.field}"

        if self.min_value is not None and value < self.min_value:
            return f"{self.field}_below_min_{self.min_value}"

        if self.max_value is not None and value > self.max_value:
            return f"{self.field}_above_max_{self.max_value}"

        return "filtered"

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        """Determine which records have values within the specified range.

        Args:
            records: List of records to filter.

        Returns:
            List of booleans indicating whether each record should be kept.
        """
        results = []

        for record in records:
            value = self._get_numeric_value(record)

            if value is None:
                # Field is missing or non-numeric
                results.append(self.keep_missing)
            else:
                # Check if value is in range
                results.append(self._is_in_range(value))

        return results

    def _process_batch_with_rejected_impl(self, records: list[dict[str, Any]]) -> BatchResult:
        """Process batch and collect rejected (filtered out) samples.

        Overrides the base Filter implementation to include:
        - Field-specific operator name (e.g., RangeFilter_video_aesthetic_score)
        - Detailed rejection reason (e.g., video_aesthetic_score_below_min_4.5)
        - The actual value that caused rejection
        """
        if not records:
            return BatchResult(passed=[], rejected=[])

        passed = []
        rejected = []

        for record in records:
            value = self._get_numeric_value(record)

            if value is None:
                keep = self.keep_missing
            else:
                keep = self._is_in_range(value)

            if keep:
                passed.append(record)
            else:
                # Add rejection metadata with field-specific details
                rejected_record = record.copy()
                rejected_record["_rejection_details"] = {
                    "reason": self._get_rejection_reason(value),
                    "operator": self.operator_name,  # Uses field-specific name from base class property
                    "field": self.field,
                    "value": value,
                    "min_value": self.min_value,
                    "max_value": self.max_value,
                }
                rejected.append(rejected_record)

        return BatchResult(passed=passed, rejected=rejected)
