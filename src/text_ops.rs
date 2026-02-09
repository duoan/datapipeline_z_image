//! Text processing operators
//!
//! Provides Rust-accelerated text operations:
//! - `html_extract_text`: Extract readable text from a single HTML string
//! - `html_extract_text_batch`: Extract readable text from multiple HTML strings (parallel)
//! - `text_repetition_keep_batch`: MassiveWeb-style text repetition keep/drop decision
//! - `text_length_keep_batch`: Text length keep/drop decision

use dom_smoothie::Readability;
use pyo3::prelude::*;
use rayon::prelude::*;
use std::collections::HashMap;
use std::panic::{self, AssertUnwindSafe};

// ============================================================================
// HTML Text Extraction
// ============================================================================

/// Extract readable text from HTML using dom_smoothie (Rust port of readability.js)
/// Uses catch_unwind to handle panics from the dom_smoothie library gracefully,
/// especially for malformed HTML or UTF-8 boundary issues with non-ASCII characters.
fn html_extract_text_core(html: &str) -> Option<(String, String)> {
    let result = panic::catch_unwind(AssertUnwindSafe(|| {
        let mut readability = Readability::new(html, None, None).ok()?;
        let article = readability.parse().ok()?;

        let title = article.title;
        let content = article.text_content.to_string();

        // Skip if content is empty or too short
        if content.trim().is_empty() || content.len() < 50 {
            return None;
        }

        Some((title, content))
    }));

    match result {
        Ok(opt) => opt,
        Err(_) => None,
    }
}

/// Extract readable text from a single HTML string
/// Returns (title, text, text_length) or None if extraction fails
#[pyfunction]
pub fn html_extract_text(html: String) -> PyResult<Option<(String, String, usize)>> {
    match html_extract_text_core(&html) {
        Some((title, text)) => {
            let text_len = text.len();
            Ok(Some((title, text, text_len)))
        }
        None => Ok(None),
    }
}

/// Batch extract readable text from multiple HTML strings (parallel)
/// Returns Vec of (title, text, text_length) for successful extractions
#[pyfunction]
pub fn html_extract_text_batch(
    htmls: Vec<String>,
) -> PyResult<Vec<Option<(String, String, usize)>>> {
    let results: Vec<_> = htmls
        .into_par_iter()
        .map(|html| {
            html_extract_text_core(&html).map(|(title, text)| {
                let text_len = text.len();
                (title, text, text_len)
            })
        })
        .collect();
    Ok(results)
}

// ============================================================================
// Text Repetition Filter
// ============================================================================

fn extract_words_unicode(text: &str) -> Vec<String> {
    let mut words = Vec::new();
    let mut current = String::new();

    for ch in text.chars() {
        if ch.is_alphanumeric() || ch == '_' {
            current.push(ch);
        } else if !current.is_empty() {
            words.push(std::mem::take(&mut current));
        }
    }

    if !current.is_empty() {
        words.push(current);
    }

    words
}

fn rep_counter_fraction(elements: &[String], ngram_size: usize, weighted: bool) -> f64 {
    let total_elements = elements.len();
    let total_ngrams = if total_elements >= ngram_size {
        total_elements - ngram_size + 1
    } else {
        0
    };

    let lengths: Vec<usize> = elements.iter().map(|s| s.chars().count()).collect();
    let total_charlen: usize = lengths.iter().sum();

    if total_ngrams == 0 {
        return if ngram_size == 1 { 1.0 } else { 0.0 };
    }
    if total_ngrams == 1 {
        return 0.0;
    }

    let mut prefix_lengths = vec![0usize; total_elements + 1];
    for (i, len) in lengths.iter().enumerate() {
        prefix_lengths[i + 1] = prefix_lengths[i] + len;
    }

    let mut id_map: HashMap<&str, u32> = HashMap::new();
    let mut next_id: u32 = 0;
    let mut token_ids = Vec::with_capacity(total_elements);

    for element in elements {
        let key = element.as_str();
        if let Some(id) = id_map.get(key) {
            token_ids.push(*id);
        } else {
            id_map.insert(key, next_id);
            token_ids.push(next_id);
            next_id = next_id.saturating_add(1);
        }
    }

    let mut ngram_counts: HashMap<Vec<u32>, Vec<usize>> = HashMap::new();
    for start in 0..total_ngrams {
        let end = start + ngram_size;
        let ngram = token_ids[start..end].to_vec();
        ngram_counts.entry(ngram).or_default().push(start);
    }

    if ngram_size == 1 {
        if weighted {
            if total_charlen == 0 {
                return 0.0;
            }
            let mut total_repeat_len = 0usize;
            for idxs in ngram_counts.values() {
                if idxs.len() > 1 {
                    total_repeat_len += lengths[idxs[0]] * idxs.len();
                }
            }
            return total_repeat_len as f64 / total_charlen as f64;
        }

        let mut total_repeats = 0usize;
        for idxs in ngram_counts.values() {
            if idxs.len() > 1 {
                total_repeats += idxs.len();
            }
        }
        return total_repeats as f64 / total_elements as f64;
    }

    let repeated_start_idxs: Vec<usize> = if ngram_size <= 4 {
        let mut best: Option<&Vec<usize>> = None;
        let mut best_count: usize = 0;
        let mut best_char_len: usize = 0;

        for idxs in ngram_counts.values() {
            let count = idxs.len();
            if count <= 1 {
                continue;
            }
            let start = idxs[0];
            let char_len = prefix_lengths[start + ngram_size] - prefix_lengths[start];

            if count > best_count || (count == best_count && char_len > best_char_len) {
                best = Some(idxs);
                best_count = count;
                best_char_len = char_len;
            }
        }

        match best {
            Some(v) => v.clone(),
            None => Vec::new(),
        }
    } else {
        let mut all = Vec::new();
        for idxs in ngram_counts.values() {
            if idxs.len() > 1 {
                all.extend(idxs.iter().copied());
            }
        }
        all
    };

    if total_charlen == 0 {
        return 0.0;
    }

    let mut repeat_mask = vec![false; total_elements];
    for start in repeated_start_idxs {
        let end = (start + ngram_size).min(total_elements);
        for idx in start..end {
            repeat_mask[idx] = true;
        }
    }

    let mut repeat_len = 0usize;
    for (idx, repeated) in repeat_mask.iter().enumerate() {
        if *repeated {
            repeat_len += lengths[idx];
        }
    }

    repeat_len as f64 / total_charlen as f64
}

fn should_keep_text(text: &str) -> bool {
    let lines: Vec<String> = text
        .split('\n')
        .filter(|line| !line.is_empty())
        .map(ToOwned::to_owned)
        .collect();

    let paragraphs: Vec<String> = text
        .split("\n\n")
        .filter(|paragraph| !paragraph.is_empty())
        .map(ToOwned::to_owned)
        .collect();

    let words = extract_words_unicode(text);

    let checks: [(&[String], usize, bool, f64); 13] = [
        (&lines, 1, false, 0.3),
        (&paragraphs, 1, false, 0.3),
        (&lines, 1, true, 0.2),
        (&paragraphs, 1, true, 0.2),
        (&words, 2, true, 0.2),
        (&words, 3, true, 0.18),
        (&words, 4, true, 0.16),
        (&words, 5, true, 0.15),
        (&words, 6, true, 0.14),
        (&words, 7, true, 0.13),
        (&words, 8, true, 0.12),
        (&words, 9, true, 0.11),
        (&words, 10, true, 0.10),
    ];

    for (elements, ngram_size, weighted, upper_bound) in checks {
        let rep_frac = rep_counter_fraction(elements, ngram_size, weighted);
        if rep_frac > upper_bound {
            return false;
        }
    }

    true
}

/// Batch text repetition keep/drop decision, aligned with TextRepetitionFilter logic.
#[pyfunction]
pub fn text_repetition_keep_batch(texts: Vec<String>) -> PyResult<Vec<bool>> {
    let results: Vec<bool> = texts
        .into_par_iter()
        .map(|text| should_keep_text(&text))
        .collect();
    Ok(results)
}

// ============================================================================
// Text Length Filter
// ============================================================================

fn is_punctuation_ascii(ch: char) -> bool {
    ch.is_ascii_punctuation()
}

fn count_words(text: &str, ignore_punctuation: bool) -> usize {
    let mut count = 0usize;
    let mut in_word = false;

    for ch in text.chars() {
        if ch.is_alphanumeric() {
            if !in_word {
                count += 1;
                in_word = true;
            }
        } else if !ignore_punctuation && is_punctuation_ascii(ch) {
            count += 1;
            in_word = false;
        } else {
            in_word = false;
        }
    }
    count
}

fn count_sentences(text: &str) -> usize {
    if text.trim().is_empty() {
        return 0;
    }
    let punct_count = text
        .chars()
        .filter(|ch| matches!(ch, '.' | '!' | '?'))
        .count();
    std::cmp::max(1, punct_count)
}

fn count_lines(text: &str) -> usize {
    text.lines().count()
}

fn count_paragraphs(text: &str) -> usize {
    if text.trim().is_empty() {
        return 0;
    }
    let count = text
        .split("\n\n")
        .filter(|paragraph| !paragraph.trim().is_empty())
        .count();
    std::cmp::max(1, count)
}

fn count_chars(text: &str, ignore_punctuation: bool) -> usize {
    if ignore_punctuation {
        text.chars().filter(|ch| ch.is_alphanumeric()).count()
    } else {
        text.chars().count()
    }
}

fn calculate_length(text: &str, length_type: &str, ignore_punctuation: bool) -> Option<usize> {
    match length_type {
        "char" => Some(count_chars(text, ignore_punctuation)),
        "word" => Some(count_words(text, ignore_punctuation)),
        "sentence" => Some(count_sentences(text)),
        "line" => Some(count_lines(text)),
        "paragraph" => Some(count_paragraphs(text)),
        _ => None,
    }
}

/// Batch text length keep/drop decision.
#[pyfunction]
pub fn text_length_keep_batch(
    texts: Vec<String>,
    min_length: i64,
    max_length: Option<i64>,
    length_type: String,
    ignore_punctuation: bool,
) -> PyResult<Vec<bool>> {
    let results: Vec<bool> = texts
        .into_par_iter()
        .map(|text| {
            let maybe_len = calculate_length(&text, &length_type, ignore_punctuation);
            let len = maybe_len.unwrap_or(0) as i64;
            if len < min_length {
                return false;
            }
            if let Some(max_len) = max_length {
                return len <= max_len;
            }
            true
        })
        .collect();
    Ok(results)
}
