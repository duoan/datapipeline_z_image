"""MassiveWeb-style text repetition filter."""

import re
from collections import defaultdict
from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"
UNICODE_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


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
        ngram_counts: dict[tuple[tuple[str, ...], int], list[int]] = defaultdict(list)
        total_elements = len(elements)
        total_ngrams = 0
        total_charlen = sum(len(v) for v in elements)

        for idx in range(total_elements):
            start = idx + 1 - ngram_size
            if start < 0:
                continue
            ngram = tuple(elements[start : idx + 1])
            char_len = sum(len(part) for part in ngram)
            ngram_counts[(ngram, char_len)].append(start)
            total_ngrams += 1

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
                    char_len * len(idxs)
                    for (_ngram, char_len), idxs in ngram_counts.items()
                    if len(idxs) > 1
                )
                return total_repeat_len / total_charlen

            total_repeats = sum(len(idxs) for idxs in ngram_counts.values() if len(idxs) > 1)
            return total_repeats / total_elements

        # Ngram size > 1 case:
        # If ngram size <= 4, only use the most common repeating ngram start positions.
        # Otherwise, use all repeating ngram start positions.
        repeated_start_idxs: list[int]
        if ngram_size <= 4:
            repeated_entries = [
                (key, idxs) for key, idxs in ngram_counts.items() if len(idxs) > 1
            ]
            if repeated_entries:
                key, idxs = max(repeated_entries, key=lambda item: (len(item[1]), item[0][1]))
                _ = key
                repeated_start_idxs = list(idxs)
            else:
                repeated_start_idxs = []
        else:
            repeated_start_idxs = [
                idx for idxs in ngram_counts.values() if len(idxs) > 1 for idx in idxs
            ]

        repeat_element_idxs: set[int] = set()
        for start in repeated_start_idxs:
            repeat_element_idxs.update(range(start, start + ngram_size))

        if total_charlen == 0:
            return 0.0
        repeat_len = sum(len(elements[idx]) for idx in repeat_element_idxs if idx < total_elements)
        return repeat_len / total_charlen

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        results: list[bool] = []
        for record in records:
            text = self._get_text(record)
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

            keep = True
            for elements, ngram_size, weighted, upper_bound in flow_args:
                rep_frac = self._rep_counter_fraction(elements, ngram_size, weighted)
                if rep_frac > upper_bound:
                    keep = False
                    break
            results.append(keep)

        return results
