import mega_data_factory.operators.filters.text_repetition_filter as repetition_module
from mega_data_factory.operators.filters.text_repetition_filter import TextRepetitionFilter


def test_text_repetition_flags_obvious_repetition():
    f = TextRepetitionFilter()
    records = [
        {"text": "this is a normal sentence with enough variety"},
        {"text": "spam spam spam spam spam spam spam spam"},
    ]
    keep_flags = f.should_keep_batch(records)
    assert keep_flags == [True, False]


def test_text_repetition_handles_bytes_and_non_string_values():
    f = TextRepetitionFilter()
    records = [
        {"text": b"alpha beta gamma"},
        {"text": 12345},
    ]
    keep_flags = f.should_keep_batch(records)
    assert keep_flags == [True, True]


def test_text_repetition_python_and_rust_match_when_available():
    f = TextRepetitionFilter()
    records = [
        {"text": "line1\nline2\nline3"},
        {"text": "x\nx\nx\nx\nx"},
        {"text": "a b c d e f g h i j"},
        {"text": "foo bar foo bar foo bar foo bar"},
    ]

    texts = [f._get_text(r) for r in records]
    python_result = [f._should_keep_python(text) for text in texts]

    if repetition_module.RUST_TEXT_REPETITION_AVAILABLE and repetition_module._keep_batch_rust:
        rust_result = list(repetition_module._keep_batch_rust(texts))
        assert rust_result == python_result


def test_text_repetition_fallback_when_rust_unavailable(monkeypatch):
    monkeypatch.setattr(repetition_module, "RUST_TEXT_REPETITION_AVAILABLE", False)
    monkeypatch.setattr(repetition_module, "_keep_batch_rust", None)

    f = TextRepetitionFilter()
    records = [{"text": "hello world"}, {"text": "repeat repeat repeat repeat"}]
    try:
        f.should_keep_batch(records)
        assert False, "Expected RuntimeError when Rust backend is unavailable"
    except RuntimeError as e:
        assert "requires Rust backend" in str(e)
