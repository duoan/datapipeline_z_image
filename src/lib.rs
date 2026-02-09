//! Mega Data Factory - Rust Accelerated Operators
//!
//! This crate provides high-performance operators for data processing:
//!
//! ## Image Operations (`image_ops`)
//! - `image_assess_quality_batch`: Compression artifacts + entropy calculation
//! - `image_compute_phash_batch`: Perceptual hash computation
//!
//! ## Text Operations (`text_ops`)
//! - `html_extract_text`: Extract readable text from a single HTML string
//! - `html_extract_text_batch`: Extract readable text from multiple HTML strings (parallel)
//! - `text_repetition_keep_batch`: MassiveWeb-style text repetition keep/drop decision
//! - `text_length_keep_batch`: Text length keep/drop decision

mod image_ops;
mod text_ops;

use pyo3::prelude::*;

// Re-export all public functions
pub use image_ops::{image_assess_quality_batch, image_compute_phash_batch};
pub use text_ops::{
    html_extract_text, html_extract_text_batch, text_length_keep_batch, text_repetition_keep_batch,
};

/// Python module definition
#[pymodule]
fn rust_operators(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Image operations
    m.add_function(wrap_pyfunction!(image_ops::image_assess_quality_batch, m)?)?;
    m.add_function(wrap_pyfunction!(image_ops::image_compute_phash_batch, m)?)?;

    // Text operations - HTML extraction + repetition filter
    m.add_function(wrap_pyfunction!(text_ops::html_extract_text, m)?)?;
    m.add_function(wrap_pyfunction!(text_ops::html_extract_text_batch, m)?)?;
    m.add_function(wrap_pyfunction!(text_ops::text_repetition_keep_batch, m)?)?;
    m.add_function(wrap_pyfunction!(text_ops::text_length_keep_batch, m)?)?;

    Ok(())
}
