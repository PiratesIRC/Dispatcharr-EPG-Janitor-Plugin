"""Regression lock for the 3 normalize_name fixes ported from Stream-Mapparr.

Per the workspace `fuzzy_matcher.py` drift rule: matcher fixes + their regression
tests are ported to every copy until the shared-core refactor lands. Covers the
three input-cleaning fixes (bug-048 stylized-Unicode strip, bug-051 emoji-as-letter,
bug-055 numeric resolution markers). Helper-level asserts — no fixtures needed.
Unicode inputs use `\\u` escapes so an editor cannot silently strip them.
"""
import re

RAW = "\u1d3f\u1d2c\u1d42"  # superscript R A W
BALL = "\u26bd"  # SOCCER BALL (emoji-as-letter 'o')
VS16 = "\ufe0f"  # VARIATION SELECTOR-16 (zero-width)


def test_emoji_as_letter():
    import fuzzy_matcher as fm
    assert fm._normalize_emoji("SP" + BALL + "RTS") == "SPoRTS"
    assert fm._normalize_emoji("BE" + BALL) == "BE"          # edge ball stripped, not mapped
    assert fm._normalize_emoji(VS16 + "HULU") == "HULU"      # zero-width stripped
    assert fm._normalize_emoji("Fox Sports") == "Fox Sports"  # ASCII fast path


def test_stylized_decoration_strip():
    import fuzzy_matcher as fm
    assert fm._strip_stylized_tokens("WEATHERNATION " + RAW) == "WEATHERNATION"
    assert fm._strip_stylized_tokens("Gold " + RAW) == "Gold"     # ASCII tier word kept
    assert fm._strip_stylized_tokens("Fox Sports 1") == "Fox Sports 1"


def test_is_decorative_char():
    import fuzzy_matcher as fm
    assert fm._is_decorative_char("ᴿ") is True   # superscript modifier-letter R
    assert fm._is_decorative_char("G") is False
    assert fm._is_decorative_char("4") is False


def test_resolution_pattern():
    import fuzzy_matcher as fm
    assert fm.RESOLUTION_PATTERNS == [r"\b\d{3,4}[pi]\b"]
    pat = fm.RESOLUTION_PATTERNS[0]
    assert re.sub(pat, "", "ESPN 1080p", flags=re.IGNORECASE).strip() == "ESPN"
    assert re.sub(pat, "", "Channel 4", flags=re.IGNORECASE) == "Channel 4"      # bare number kept
    assert "10800" in re.sub(pat, "", "Foo 10800p", flags=re.IGNORECASE)         # 5-digit kept
    assert re.sub(pat, "", "Volume 100 I", flags=re.IGNORECASE) == "Volume 100 I"  # spaced kept
