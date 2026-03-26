from samplelib.text import normalize_whitespace


def test_normalize_whitespace_collapses_runs() -> None:
    assert normalize_whitespace("a\t  b\n\n c") == "a b c"


def test_normalize_whitespace_strips() -> None:
    assert normalize_whitespace("  hello   ") == "hello"
