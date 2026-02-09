from mega_data_factory.operators.filters.text_length_filter import TextLengthFilter


def test_char_length_uses_precomputed_field():
    f = TextLengthFilter(min_length=5, max_length=10, text_length_field="text_length")
    records = [{"text": "x", "text_length": 6}, {"text": "hello world", "text_length": 20}]
    assert f.should_keep_batch(records) == [True, False]


def test_char_length_ignores_precomputed_when_ignore_punctuation_enabled():
    f = TextLengthFilter(
        min_length=3,
        max_length=3,
        length_type="char",
        ignore_punctuation=True,
        text_length_field="text_length",
    )
    records = [{"text": "a,b!", "text_length": 100}]
    assert f.should_keep_batch(records) == [False]


def test_char_length_ignore_punctuation():
    f = TextLengthFilter(min_length=4, max_length=4, length_type="char", ignore_punctuation=True)
    records = [{"text": "a,b!2"}]  # alnum chars: a, b, 2 -> 3
    assert f.should_keep_batch(records) == [False]

    f2 = TextLengthFilter(min_length=5, max_length=5, length_type="char", ignore_punctuation=False)
    assert f2.should_keep_batch(records) == [True]


def test_word_length_modes():
    records = [{"text": "hello, world!"}]

    f = TextLengthFilter(min_length=2, max_length=2, length_type="word", ignore_punctuation=True)
    assert f.should_keep_batch(records) == [True]

    f2 = TextLengthFilter(min_length=4, max_length=4, length_type="word", ignore_punctuation=False)
    assert f2.should_keep_batch(records) == [True]  # "hello" "," "world" "!"


def test_sentence_line_paragraph_modes():
    text = "First line.\nSecond line!\n\nThird block?"
    records = [{"text": text}]

    sentence_filter = TextLengthFilter(min_length=3, max_length=3, length_type="sentence")
    line_filter = TextLengthFilter(min_length=4, max_length=4, length_type="line")
    paragraph_filter = TextLengthFilter(min_length=2, max_length=2, length_type="paragraph")

    assert sentence_filter.should_keep_batch(records) == [True]
    assert line_filter.should_keep_batch(records) == [True]
    assert paragraph_filter.should_keep_batch(records) == [True]


def test_lower_upper_bound_aliases_take_precedence():
    f = TextLengthFilter(
        min_length=100,
        max_length=200,
        lower_bound=2,
        upper_bound=3,
        length_type="word",
    )
    records = [{"text": "one two"}, {"text": "one two three four"}]
    assert f.should_keep_batch(records) == [True, False]


def test_invalid_length_type_raises():
    try:
        TextLengthFilter(length_type="token")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "length_type must be one of" in str(e)
