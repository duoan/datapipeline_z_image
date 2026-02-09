"""MassiveWeb-style text repetition filter."""

import re
from collections import defaultdict
from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"
UNICODE_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)

# Try to load Rust backend (optional acceleration)
RUST_TEXT_REPETITION_AVAILABLE = False
_keep_batch_rust = None

try:
    from mega_data_factory import rust_operators as _rust_module  # type: ignore

    _keep_batch_rust = getattr(_rust_module, "text_repetition_keep_batch", None)
    if _keep_batch_rust is not None:
        RUST_TEXT_REPETITION_AVAILABLE = True
except ImportError:
    pass


class TextRepetitionFilter(Filter):
    """Filter repetitive text using multiple line/paragraph/word repetition checks."""

    def __init__(self, text_field: str = FIELD_TEXT):
        super().__init__()
        self.text_field = text_field

    def _get_text(self, record: dict[str, Any]) -> str:
        value = record.get(self.text_field)
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _rep_counter_fraction(elements: list[str], ngram_size: int, weighted: bool) -> float:
        ngram_counts: dict[tuple[str, ...], list[int]] = defaultdict(list)
        total_elements = len(elements)
        total_ngrams = total_elements - ngram_size + 1 if total_elements >= ngram_size else 0
        lengths = [len(v) for v in elements]
        total_charlen = sum(lengths)

        # Prefix sums for O(1) n-gram char length lookup.
        prefix_lengths = [0] * (total_elements + 1)
        for idx, length in enumerate(lengths):
            prefix_lengths[idx + 1] = prefix_lengths[idx] + length

        for start in range(total_ngrams):
            end = start + ngram_size
            ngram = tuple(elements[start:end])
            ngram_counts[ngram].append(start)

        # Special cases: either 0 or 1 ngrams
        if total_ngrams == 0:
            return 1.0 if ngram_size == 1 else 0.0
        if total_ngrams == 1:
            return 0.0

        if ngram_size == 1:
            if weighted:
                if total_charlen == 0:
                    return 0.0
                total_repeat_len = sum(
                    lengths[idxs[0]] * len(idxs) for idxs in ngram_counts.values() if len(idxs) > 1
                )
                return total_repeat_len / total_charlen

            total_repeats = sum(len(idxs) for idxs in ngram_counts.values() if len(idxs) > 1)
            return total_repeats / total_elements

        # Ngram size > 1 case:
        # If ngram size <= 4, only use the most common repeating ngram start positions.
        # Otherwise, use all repeating ngram start positions.
        repeated_start_idxs: list[int]
        if ngram_size <= 4:
            best_key = None
            best_idxs = None
            best_count = 0
            best_char_len = -1
            for key, idxs in ngram_counts.items():
                count = len(idxs)
                if count <= 1:
                    continue
                key_start = idxs[0]
                key_char_len = prefix_lengths[key_start + ngram_size] - prefix_lengths[key_start]
                if count > best_count or (count == best_count and key_char_len > best_char_len):
                    best_key = key
                    best_idxs = idxs
                    best_count = count
                    best_char_len = key_char_len
            _ = best_key
            repeated_start_idxs = list(best_idxs) if best_idxs else []
        else:
            repeated_start_idxs = [idx for idxs in ngram_counts.values() if len(idxs) > 1 for idx in idxs]

        repeat_mask = bytearray(total_elements)
        for start in repeated_start_idxs:
            end = min(start + ngram_size, total_elements)
            for idx in range(start, end):
                repeat_mask[idx] = 1

        if total_charlen == 0:
            return 0.0
        repeat_len = sum(lengths[idx] for idx, repeated in enumerate(repeat_mask) if repeated)
        return repeat_len / total_charlen

    def _should_keep_python(self, text: str) -> bool:
        lines = [line for line in text.split("\n") if line]
        paragraphs = [paragraph for paragraph in text.split("\n\n") if paragraph]
        words = UNICODE_WORD_RE.findall(text)

        flow_args: list[tuple[list[str], int, bool, float]] = [
            (lines, 1, False, 0.3),
            (paragraphs, 1, False, 0.3),
            (lines, 1, True, 0.2),
            (paragraphs, 1, True, 0.2),
            (words, 2, True, 0.2),
            (words, 3, True, 0.18),
            (words, 4, True, 0.16),
            (words, 5, True, 0.15),
            (words, 6, True, 0.14),
            (words, 7, True, 0.13),
            (words, 8, True, 0.12),
            (words, 9, True, 0.11),
            (words, 10, True, 0.10),
        ]

        for elements, ngram_size, weighted, upper_bound in flow_args:
            rep_frac = self._rep_counter_fraction(elements, ngram_size, weighted)
            if rep_frac > upper_bound:
                return False
        return True

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        if not records:
            return []

        texts = [self._get_text(record) for record in records]

        if not (RUST_TEXT_REPETITION_AVAILABLE and _keep_batch_rust):
            raise RuntimeError(
                "TextRepetitionFilter requires Rust backend: mega_data_factory.rust_operators.text_repetition_keep_batch"
            )

        return list(_keep_batch_rust(texts))
