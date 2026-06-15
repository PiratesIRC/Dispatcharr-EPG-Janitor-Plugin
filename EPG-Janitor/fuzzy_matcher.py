"""
Fuzzy Matcher Module for EPG-Janitor (Dispatcharr plugin).

Two subsystems in one class for 1.26.0:

1. Lineuparr-ported matching pipeline:
   - alias -> exact -> substring -> fuzzy token-sort
   - length-scaled thresholds, token-overlap guards
   - East/West/Pacific regional differentiation (toggle-aware via user_ignored_tags)
   - Normalization caching via precompute_normalizations()
   - match_all_streams() returns ranked [(name, score, match_type), ...]

2. EPG-Janitor legacy callsign/channel-database helpers:
   - extract_callsign, _load_channel_databases, reload_databases,
     match_broadcast_channel, find_best_match, get_category_for_channel,
     normalize_callsign, extract_tags, build_final_channel_name.

A future refactor may split the two subsystems into separate modules.
"""

import json
import logging
import os
import re
import unicodedata
from glob import glob

# Optional C-accelerated Levenshtein. When present, the matcher uses rapidfuzz's
# normalized_similarity (1 - distance/max(len)); the pure-Python fallback below
# computes the identical value (bug-026). rapidfuzz is an OPTIONAL runtime dep —
# absence simply falls back to pure Python. (dev/CI installs it via requirements-dev.txt.)
try:
    from rapidfuzz.distance import Levenshtein as _rf_lev
    _USE_RAPIDFUZZ = True
except ImportError:
    _USE_RAPIDFUZZ = False

__version__ = "1.26.1660712"

LOGGER = logging.getLogger("plugins.epg_janitor.fuzzy_matcher")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.DEBUG)

# --- Pattern categories for normalization ---

# Merged pattern set — Lineuparr base + EPG-Janitor bracketed variants.
# All patterns applied with re.IGNORECASE in normalize_name().

QUALITY_PATTERNS = [
    # Bracketed: [4K], [UHD], [FHD], [HD], [SD], [FD], [8K], [Unknown], [Unk], [Slow], [Dead], [Backup]
    r'\s*\[(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead|Backup)\]\s*',
    # Parenthesized
    r'\s*\((4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead|Backup)\)\s*',
    # Start of string
    r'^\s*(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)\b\s*',
    # End of string
    r'\s*\b(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)$',
    # Middle (with word boundary padding)
    r'\s+\b(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)\b\s+',
    # Trailing colon form: "HD:", "4K:"
    r'\b(?:4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead):\s',
]

# Numeric resolution markers the keyword QUALITY_PATTERNS miss: 720p, 1080p/i, 2160p,
# 3840P, 480p, etc. — a 3-4 digit run glued directly to p/i. The 3-digit lower bound
# excludes 2-digit noise; the 4-digit upper bound excludes 5-digit numbers (10800p won't
# match). The p/i must be GLUED to the digits (no space): real markers are always written
# "720P"/"3840P", and requiring the glue avoids stripping a spaced standalone P/I such as a
# roman numeral ("Volume 100 I"). The p/i \b anchor keeps bare numbers (1080, "Channel 4")
# intact. Applied with re.IGNORECASE in the ignore_quality block, like QUALITY_PATTERNS.
RESOLUTION_PATTERNS = [
    r'\b\d{3,4}[pi]\b',
]


# Matches "+1"/"+2" time-shift suffixes in the ORIGINAL (pre-normalization) name.
# Must be checked before normalization because "+" is preserved differently across
# paths. \d{1,2} excludes brand "+" like "Discovery+"/"Disney+". Ported from Lineuparr.
_PLUS_SHIFT_RE = re.compile(r'\+\s{0,2}\d{1,2}\b')

REGIONAL_PATTERNS = [
    # Always stripped when ignore_regional=True; these never distinguish separate feeds.
    r'\s[Pp][Aa][Cc][Ii][Ff][Ii][Cc]',
    r'\s[Cc][Ee][Nn][Tt][Rr][Aa][Ll]',
    r'\s[Mm][Oo][Uu][Nn][Tt][Aa][Ii][Nn]',
    r'\s[Aa][Tt][Ll][Aa][Nn][Tt][Ii][Cc]',
    r'\s*\([Pp][Aa][Cc][Ii][Ff][Ii][Cc]\)\s*',
    r'\s*\([Cc][Ee][Nn][Tt][Rr][Aa][Ll]\)\s*',
    r'\s*\([Mm][Oo][Uu][Nn][Tt][Aa][Ii][Nn]\)\s*',
    r'\s*\([Aa][Tt][Ll][Aa][Nn][Tt][Ii][Cc]\)\s*',
]

REGIONAL_EAST_WEST_PATTERNS = [
    # Stripped only when ignore_regional=True (EPG-Janitor default).
    # When ignore_regional=False, East/West are preserved so the regional
    # differentiation filter in match_all_streams() can act on them.
    r'\s[Ee][Aa][Ss][Tt]\b',
    r'\s[Ww][Ee][Ss][Tt]\b',
    r'\s*\([Ee][Aa][Ss][Tt]\)\s*',
    r'\s*\([Ww][Ee][Ss][Tt]\)\s*',
]

GEOGRAPHIC_PATTERNS = [
    # Bracket/delimiter country-code prefixes
    r'\b[A-Z]{2,3}:\s*',
    r'\b[A-Z]{2,3}\s*-\s*',
    r'\|[A-Z]{2,3}\|\s*',
    r'\[[A-Z]{2,3}\]\s*',
    # EPG-Janitor legacy: bare "US " / "USA " at word boundary. The NETWORK
    # negative-lookahead protects the real channel "USA Network" (was mis-stripped
    # to "Network"). Case-insensitive because GEOGRAPHIC_PATTERNS run with re.IGNORECASE.
    r'\bUSA?:\s(?!network\b|open\b)',
    r'\bUSA?\s(?!network\b|open\b)',
]

PROVIDER_PREFIX_PATTERNS = [
    r'^(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*[:\-\|]\s*',
    r'^\s*\((?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\)\s*',
    r'\s*\|\s*(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*$',
    # Country code glued to a quality tag, no separator word
    # ("UKSD: Sky Sports", "UKHD ESPN"). Ported from Lineuparr.
    r'^(?:US|UK)(?:SD|HD|FHD|UHD|FD|HEVC|4K|8K)\b\s*[:\-\|]?\s*',
    # Bare country tag + whitespace, no separator ("US Racer", "FR beIN SPORTS").
    # TRIMMED set: UK/CA/DE/AU dropped (collide with "UK Gold"); FRA/GER dropped
    # (zero real-DB hits, risk over-stripping "GER TV"). US guards "US Open" — a
    # tennis brand, not a country tag (the only real bare-US-prefixed DB brand).
    r'^(?:US(?!\s+open\b)|FR|MX|MEX)\s+',
    # FAST streaming-platform source tags. Separator REQUIRED so it can't eat
    # "GOLF"/"PLEX TV Movies". Ported from Lineuparr.
    r'^(?:RK|GO|TUBI|PLUTO|XUMO|PLEX|STIRR|FREEVEE|GLANCE)\s*[:\-\|]\s*',
]

MISC_PATTERNS = [
    # Single-letter parenthesized tags: (A), (B), (C)
    r'\s*\([A-Z]\)\s*',
    # Cinemax/specialty
    r'\s*\(CX\)\s*',
    # Any remaining parenthesized group (broad Lineuparr-style fallback)
    r'\s*\([^)]*\)\s*',
]


# Spelled-out number -> digit, so "BBC Three" matches "BBC 3" and
# "Three Angels Broadcasting" matches "3 Angels Broadcasting". Word boundaries
# protect brand names with embedded letters ("Onesimus"). Ported from Channel-Maparr.
NUM_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12",
}
NUM_WORDS_RE = re.compile(
    r'\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b',
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Stylized-Unicode decoration stripping
# --------------------------------------------------------------------------- #
# Streams tag names with stylized-Unicode tier/format markers (superscript
# "WEATHERNATION RAW", small-cap "FHD", bullet-prefixed "CNN") that the ASCII tag
# regexes below cannot see. We drop whole tokens that are pure decoration BEFORE
# the ASCII pipeline runs. Detection is by Unicode character *name* (not code-point
# ranges), so it covers superscripts, "modifier letter" superscript capitals, and
# Latin small-caps wherever they live (e.g. small-cap H is U+029C in IPA Extensions
# and modifier V is U+2C7D in Latin-Ext-C, both outside the obvious blocks).

# Ornament glyphs whose Unicode name carries no decoration keyword.
_DECORATIVE_SYMBOLS = frozenset("◉")  # FISHEYE; add individual chars (not strings) here


def _is_decorative_char(ch):
    """True for a stylized letterform/ornament that carries no semantic content in a
    channel name (superscripts, subscripts, modifier-letter superscript capitals,
    Latin small-capitals, curated bullets). ASCII and ordinary letters return False."""
    if ch.isascii():
        return False
    if ch in _DECORATIVE_SYMBOLS:
        return True
    try:
        nm = unicodedata.name(ch)
    except ValueError:
        # unnamed code point (control char / lone surrogate) -> not decoration
        return False
    return ('SUPERSCRIPT' in nm or 'SUBSCRIPT' in nm
            or 'SMALL CAPITAL' in nm or 'MODIFIER LETTER' in nm)


def _strip_stylized_tokens(name):
    """Drop whitespace tokens that are pure stylized decoration, then NFKD-canonicalize
    the remainder. A token is decoration when it has >=1 decorative char, no ASCII
    alphanumeric, and every char is decorative or ASCII punctuation (so a bullet glued
    to a colon, or "HD/RAW" written in superscripts, are dropped too). Real ASCII words
    (Gold/VIP) and non-Latin letters (Arabic/Cyrillic/CJK) are always kept. ASCII-only
    input is returned unchanged via the fast path (no per-char work; NFKD is a no-op
    on ASCII, so skipping it changes nothing)."""
    if name.isascii():
        return name
    kept = []
    for tok in name.split():
        has_decorative = any(_is_decorative_char(c) for c in tok)
        has_ascii_alnum = any(c.isascii() and c.isalnum() for c in tok)
        only_decorative_or_punct = all(
            _is_decorative_char(c) or (c.isascii() and not c.isalnum()) for c in tok
        )
        if has_decorative and only_decorative_or_punct and not has_ascii_alnum:
            continue  # pure decoration -> drop the whole token
        kept.append(tok)
    return unicodedata.normalize('NFKD', ' '.join(kept))


# --------------------------------------------------------------------------- #
# Emoji-as-letter + emoji decoration normalization
# --------------------------------------------------------------------------- #
# Some streams use an emoji AS A LETTER inside a word: "SP⚽RTS" / "Sp⚽rts" where the
# soccer ball stands in for 'o' (= SPORTS, the beIN family). _strip_stylized_tokens keeps
# the token (it has ASCII alnum) and process_string_for_matching would turn the ball into a
# space ("sp rts"), so it never matches "sports". We substitute the glyph for the letter it
# replaces (only when flanked by ASCII letters) and strip emoji used purely as decoration.

# Emoji that visually replace an ASCII letter when embedded in a word. Extensible.
_EMOJI_LETTER_MAP = {'⚽': 'o'}            # SOCCER BALL = 'o'  (SP⚽RTS -> SPORTS)
# Pictographic ornaments to delete. NOTE: ⚽ is intentionally in BOTH maps — the letter
# map handles it mid-word (-> 'o'); here it catches any ⚽ NOT flanked by ASCII letters
# (standalone/edge), which the substitution above leaves untouched.
_EMOJI_ORNAMENTS = frozenset('♬☾⚽')       # beamed notes, last-quarter moon, soccer ball
# Zero-width / invisible code points that only add noise to a name.
_ZERO_WIDTH = ('️', '‍')         # VARIATION SELECTOR-16, ZERO WIDTH JOINER


def _normalize_emoji(name):
    """Map emoji-as-letters to their letter and strip emoji decoration.

    The letter substitution fires ONLY when the glyph is flanked by ASCII letters
    (so "SP⚽RTS" -> "SPoRTS" but a standalone/edge "⚽" is treated as decoration and
    dropped). Zero-width selectors and ornament pictographs are deleted outright.
    ASCII-only input is returned unchanged (no emoji possible)."""
    if name.isascii():
        return name
    for zw in _ZERO_WIDTH:
        if zw in name:
            name = name.replace(zw, '')
    for glyph, letter in _EMOJI_LETTER_MAP.items():
        if glyph in name:
            name = re.sub(r'(?<=[A-Za-z])' + re.escape(glyph) + r'(?=[A-Za-z])', letter, name)
    if any(c in _EMOJI_ORNAMENTS for c in name):
        name = ''.join(c for c in name if c not in _EMOJI_ORNAMENTS)
    return name


class FuzzyMatcher:
    """Handles fuzzy matching for Lineuparr with alias support and channel number boosting."""

    def __init__(self, plugin_dir=None, match_threshold=80, logger=None):
        self.plugin_dir = plugin_dir
        self.match_threshold = match_threshold
        self.logger = logger or LOGGER
        # Cache for pre-normalized stream names (performance optimization)
        self._norm_cache = {}  # raw_name -> normalized_lower
        self._norm_nospace_cache = {}  # raw_name -> normalized_nospace
        self._processed_cache = {}  # raw_name -> processed_for_matching
        self._callsign_cache = {}  # raw_name -> (callsign|None, is_high_confidence)
        # (legacy extract_callsign callers also populate this; safe — extraction is pure)
        # Legacy EPG-Janitor state used by restored methods below
        self.broadcast_channels = []
        self.premium_channels = []
        self.premium_channels_full = []
        self.channel_lookup = {}
        self._known_callsigns = None  # lazily built allowlist of DB station callsigns
        self.country_codes = None
        self.ignore_quality = True
        self.ignore_regional = True
        self.ignore_geographic = True
        self.ignore_misc = True

    def precompute_normalizations(self, names, user_ignored_tags=None):
        """
        Pre-normalize a list of names and cache the results.
        Dramatically improves performance by avoiding redundant normalization
        when matching many lineup channels against the same stream list.
        """
        self._norm_cache.clear()
        self._norm_nospace_cache.clear()
        self._processed_cache.clear()
        self._callsign_cache.clear()

        for name in names:
            norm = self.normalize_name(name, user_ignored_tags)
            if norm and len(norm) >= 2:
                norm_lower = norm.lower()
                self._norm_cache[name] = norm_lower
                self._norm_nospace_cache[name] = re.sub(r'[\s&\-]+', '', norm_lower)
                self._processed_cache[name] = self.process_string_for_matching(norm)

        self.logger.info(f"Pre-normalized {len(self._norm_cache)} stream names (from {len(names)} total)")

    def _get_cached_norm(self, name, user_ignored_tags=None):
        """Get cached normalization or compute on the fly."""
        if name in self._norm_cache:
            return self._norm_cache[name], self._norm_nospace_cache[name]
        norm = self.normalize_name(name, user_ignored_tags)
        if not norm or len(norm) < 2:
            return None, None
        norm_lower = norm.lower()
        return norm_lower, re.sub(r'[\s&\-]+', '', norm_lower)

    def _get_cached_processed(self, name, user_ignored_tags=None):
        """Get cached processed string or compute on the fly."""
        if name in self._processed_cache:
            return self._processed_cache[name]
        norm = self.normalize_name(name, user_ignored_tags)
        if not norm or len(norm) < 2:
            return None
        return self.process_string_for_matching(norm)

    # --- Restored EPG-Janitor-specific methods ---

    def _load_channel_databases(self):
        """Load all *_channels.json files from the plugin directory."""
        pattern = os.path.join(self.plugin_dir, "*_channels.json")
        channel_files = glob(pattern)

        if not channel_files:
            self.logger.warning(f"No *_channels.json files found in {self.plugin_dir}")
            return False

        self.logger.info(f"Found {len(channel_files)} channel database file(s): {[os.path.basename(f) for f in channel_files]}")

        total_broadcast = 0
        total_premium = 0

        for channel_file in channel_files:
            try:
                with open(channel_file, encoding='utf-8') as f:
                    data = json.load(f)
                    # Extract the channels array from the JSON structure
                    channels_list = data.get('channels', []) if isinstance(data, dict) else data

                file_broadcast = 0
                file_premium = 0

                for channel in channels_list:
                    channel_type = channel.get('type', '').lower()

                    if 'broadcast' in channel_type or channel_type == 'broadcast (ota)':
                        # Broadcast channel with callsign
                        self.broadcast_channels.append(channel)
                        file_broadcast += 1

                        # Create lookup by callsign
                        callsign = channel.get('callsign', '').strip()
                        if callsign:
                            self.channel_lookup[callsign] = channel

                            # Also store base callsign without suffix for easier matching
                            base_callsign = re.sub(r'-(?:TV|CD|LP|DT|LD)$', '', callsign)
                            if base_callsign != callsign:
                                self.channel_lookup[base_callsign] = channel
                    else:
                        # Premium/cable/national channel
                        channel_name = channel.get('channel_name', '').strip()
                        if channel_name:
                            self.premium_channels.append(channel_name)
                            self.premium_channels_full.append(channel)
                            file_premium += 1

                total_broadcast += file_broadcast
                total_premium += file_premium

                self.logger.info(f"Loaded from {os.path.basename(channel_file)}: {file_broadcast} broadcast, {file_premium} premium channels")

            except Exception as e:
                self.logger.error(f"Error loading {channel_file}: {e}")

        self.logger.info(f"Total channels loaded: {total_broadcast} broadcast, {total_premium} premium")
        return True

    def reload_databases(self, country_codes=None):
        """
        Reload channel databases with specific country codes.

        Args:
            country_codes: List of country codes to load (e.g., ['US', 'UK', 'CA'])
                          If None, loads all available databases.

        Returns:
            bool: True if databases were loaded successfully, False otherwise
        """
        # Clear existing channel data
        self.broadcast_channels = []
        self.premium_channels = []
        self.premium_channels_full = []
        self.channel_lookup = {}
        self._known_callsigns = None  # rebuilt lazily from the freshly loaded DBs

        # Update country_codes tracking
        self.country_codes = country_codes

        # Determine which files to load
        if country_codes:
            # Load only specified country databases
            channel_files = []
            for code in country_codes:
                file_path = os.path.join(self.plugin_dir, f"{code}_channels.json")
                if os.path.exists(file_path):
                    channel_files.append(file_path)
                else:
                    self.logger.warning(f"Channel database not found: {code}_channels.json")
        else:
            # Load all available databases
            pattern = os.path.join(self.plugin_dir, "*_channels.json")
            channel_files = glob(pattern)

        if not channel_files:
            self.logger.warning("No channel database files found to load")
            return False

        self.logger.info(f"Loading {len(channel_files)} channel database file(s): {[os.path.basename(f) for f in channel_files]}")

        total_broadcast = 0
        total_premium = 0

        for channel_file in channel_files:
            try:
                with open(channel_file, encoding='utf-8') as f:
                    data = json.load(f)
                    # Extract the channels array from the JSON structure
                    channels_list = data.get('channels', []) if isinstance(data, dict) else data

                file_broadcast = 0
                file_premium = 0

                for channel in channels_list:
                    channel_type = channel.get('type', '').lower()

                    if 'broadcast' in channel_type or channel_type == 'broadcast (ota)':
                        # Broadcast channel with callsign
                        self.broadcast_channels.append(channel)
                        file_broadcast += 1

                        # Create lookup by callsign
                        callsign = channel.get('callsign', '').strip()
                        if callsign:
                            self.channel_lookup[callsign] = channel

                            # Also store base callsign without suffix for easier matching
                            base_callsign = re.sub(r'-(?:TV|CD|LP|DT|LD)$', '', callsign)
                            if base_callsign != callsign:
                                self.channel_lookup[base_callsign] = channel
                    else:
                        # Premium/cable/national channel
                        channel_name = channel.get('channel_name', '').strip()
                        if channel_name:
                            self.premium_channels.append(channel_name)
                            self.premium_channels_full.append(channel)
                            file_premium += 1

                total_broadcast += file_broadcast
                total_premium += file_premium

                self.logger.info(f"Loaded from {os.path.basename(channel_file)}: {file_broadcast} broadcast, {file_premium} premium channels")

            except Exception as e:
                self.logger.error(f"Error loading {channel_file}: {e}")

        self.logger.info(f"Total channels loaded: {total_broadcast} broadcast, {total_premium} premium")
        return True

    # Words that match the callsign regex shape but are never US broadcast
    # callsigns. WWE/WWF/WCW added to stop wrestling show names from being
    # extracted as false-positive callsigns (e.g., "PPV 14 | WWE NXT").
    # A US callsign (K/W + 2-4 letters) is shape-identical to many common
    # English words, so the loose Priority-4 pattern mis-extracts them — e.g.
    # the word "with" in "Bizarre Foods with Andrew Zimmern" becomes callsign
    # "WITH". Regex alone cannot tell "WITH" from "WABC"; frequent K/W-initial
    # words are denied explicitly so they never extract as a callsign.
    _CALLSIGN_DENYLIST = frozenset({
        'WWE', 'WWF', 'WCW', 'EAST',
        'WAR', 'WARS', 'WARM', 'WASH', 'WATCH', 'WAVE', 'WAVES', 'WAY', 'WAYS',
        'WEB', 'WEEK', 'WELL', 'WENT', 'WERE', 'WEST', 'WHAT', 'WHEN', 'WHERE',
        'WHICH', 'WHILE', 'WHITE', 'WHO', 'WHY', 'WIDE', 'WIFE', 'WILD', 'WILL',
        'WIND', 'WINE', 'WING', 'WINGS', 'WINS', 'WIRE', 'WISE', 'WISH', 'WITH',
        'WOLF', 'WOMAN', 'WOMEN', 'WOOD', 'WORD', 'WORDS', 'WORK', 'WORKS',
        'WORLD', 'WORM', 'WORN', 'WRAP',
        'KEEN', 'KEEP', 'KEPT', 'KEY', 'KEYS', 'KICK', 'KID', 'KIDS', 'KILL',
        'KIND', 'KING', 'KINGS', 'KISS', 'KITE', 'KNEE', 'KNEW', 'KNOW', 'KNOWN',
    })

    def _get_known_callsigns(self):
        """Allowlist of callsigns KNOWN from the loaded channel databases — the
        leading callsign of any station-format DB name ("KGTV (ABC)", "WPLG-DT").
        Used to validate that a leading callsign-shaped token is a REAL station
        (not a callsign-shaped English word like "KILN"/"WHIP") before promoting
        it to high confidence in Priority 3. Built lazily and cached; empty until
        reload_databases() loads a country DB (then Priority 3 simply never fires,
        which is the safe default). Station-format only — a callsign must be
        followed by '(' or '-' so words like "WORLD Fishing Network" are excluded.
        """
        if self._known_callsigns is None:
            cs = set()
            for ch in (self.premium_channels_full or []):
                name = (ch.get('channel_name') or '').upper() if isinstance(ch, dict) else str(ch).upper()
                m = re.match(r'([KW][A-Z]{2,4})(?:-(?:TV|CD|LP|DT|LD)\d?)?\s*[(\-]', name)
                if m:
                    cs.add(m.group(1))
            for ch in (self.broadcast_channels or []):
                token = (ch.get('callsign') or ch.get('channel_name') or '').upper() if isinstance(ch, dict) else str(ch).upper()
                m = re.match(r'([KW][A-Z]{2,4})\b', token)
                if m:
                    cs.add(m.group(1))
            self._known_callsigns = cs
        return self._known_callsigns

    def _compute_callsign_with_confidence(self, channel_name):
        """
        Extract US TV callsign with a confidence flag.

        Returns (callsign, is_high_confidence). High confidence = Priorities 1-4
        (parenthesized / suffixed-paren / leading-callsign-then-network /
        end-of-name). Priority 5 (any loose word) is low confidence.
        (None, False) when nothing extractable.

        Channel name is pre-processed to strip common provider prefixes
        (leading "D<digits>-" and "US"/"USA" prefixes) before matching.
        """
        # Remove common prefixes
        channel_name = re.sub(r'^D\d+-', '', channel_name)
        channel_name = re.sub(r'^USA?\s*[^a-zA-Z0-9]*\s*', '', channel_name, flags=re.IGNORECASE)

        # Priority 1: Callsigns in parentheses (most reliable)
        paren_match = re.search(r'\(([KW][A-Z]{3})(?:-[A-Z\s]+)?\)', channel_name, re.IGNORECASE)
        if paren_match:
            callsign = paren_match.group(1).upper()
            if callsign not in self._CALLSIGN_DENYLIST:
                return callsign, True

        # Priority 2: Callsigns with suffix in parentheses
        paren_suffix_match = re.search(r'\(([KW][A-Z]{2,4}-(?:TV|CD|LP|DT|LD))\)', channel_name, re.IGNORECASE)
        if paren_suffix_match:
            return paren_suffix_match.group(1).upper(), True

        # Priority 3: leading callsign immediately followed by a parenthesized
        # tag — "KSVI (ABC)", "WYTV-DT (ABC)" — the common EPG feed format (e.g.
        # jesmann-US). Promote to HIGH confidence ONLY when the leading token is a
        # KNOWN callsign from the loaded channel databases (a data-driven
        # allowlist), so callsign-shaped English words ("KILN (ABC)", "WHIP
        # (FOX)") are NOT promoted — a denylist cannot bound that open-ended set.
        # The allowlist also rescues real stations whose callsign is an English
        # word ("WAVE (NBC)"). The FULL callsign (incl. -DT2 subchannel suffix) is
        # returned so normalize_callsign keeps subchannels distinct.
        lead_net_match = re.match(
            r'\s*(([KW][A-Z]{2,4})(?:-(?:TV|CD|LP|DT|LD)\d?)?)\s*\([A-Za-z0-9]+\)',
            channel_name, re.IGNORECASE)
        if lead_net_match and lead_net_match.group(2).upper() in self._get_known_callsigns():
            return lead_net_match.group(1).upper(), True

        # Priority 4: Callsigns at the end
        end_match = re.search(r'\b([KW][A-Z]{2,4}(?:-(?:TV|CD|LP|DT|LD))?)\s*(?:\.[a-z]+)?\s*$', channel_name, re.IGNORECASE)
        if end_match:
            callsign = end_match.group(1).upper()
            if callsign not in self._CALLSIGN_DENYLIST:
                return callsign, True

        # Priority 5: Any word matching callsign pattern (low confidence)
        word_match = re.search(r'\b([KW][A-Z]{2,4}(?:-(?:TV|CD|LP|DT|LD))?)\b', channel_name, re.IGNORECASE)
        if word_match:
            callsign = word_match.group(1).upper()
            if callsign not in self._CALLSIGN_DENYLIST:
                return callsign, False

        return None, False

    def _extract_callsign_with_confidence(self, channel_name):
        """
        Cached wrapper around _compute_callsign_with_confidence.

        Extraction is pure in channel_name, so results are memoized — the
        anchor calls this once per (channel, stream) pair over a fixed
        stream list, which is otherwise massively redundant. Cache is
        cleared by precompute_normalizations (mirrors the norm caches).
        """
        cached = self._callsign_cache.get(channel_name)
        if cached is not None:
            return cached
        result = self._compute_callsign_with_confidence(channel_name)
        self._callsign_cache[channel_name] = result
        return result

    def extract_callsign(self, channel_name):
        """
        Extract US TV callsign from channel name with priority order.
        Returns None if common false positives appear alone.
        """
        callsign, _ = self._extract_callsign_with_confidence(channel_name)
        return callsign

    def normalize_callsign(self, callsign):
        """Remove suffix from callsign for display."""
        if callsign:
            callsign = re.sub(r'-(?:TV|CD|LP|DT|LD)$', '', callsign)
        return callsign

    def normalize_name(self, name, user_ignored_tags=None, ignore_quality=None, ignore_regional=None,
                       ignore_geographic=None, ignore_misc=None):
        """
        Normalize channel or stream name for matching by removing tags, prefixes, and noise.
        """
        if user_ignored_tags is None:
            user_ignored_tags = []

        # Resolve ignore flags from instance attributes if not explicitly passed
        if ignore_quality is None:
            ignore_quality = getattr(self, 'ignore_quality', True)
        if ignore_regional is None:
            ignore_regional = getattr(self, 'ignore_regional', True)
        if ignore_geographic is None:
            ignore_geographic = getattr(self, 'ignore_geographic', True)
        if ignore_misc is None:
            ignore_misc = getattr(self, 'ignore_misc', True)

        original_name = name

        # Map emoji-as-letters (⚽ = 'o' in "SP⚽RTS") and strip emoji decoration, before
        # the stylized-Unicode strip and ASCII regexes below — so "beIN SP⚽RTS" -> "beIN sports".
        name = _normalize_emoji(name)

        # Strip stylized-Unicode decoration (superscript/small-cap tier markers,
        # bullets) up front so the ASCII tag regexes below see plain text. Runs
        # unconditionally: a token written in superscript/small-caps is decoration
        # regardless of tag_handling, and it would otherwise block matches
        # (e.g. a superscript-RAW suffix never matches channel "WeatherNation").
        name = _strip_stylized_tokens(name)

        # Quality patterns FIRST (before space normalization)
        if ignore_quality:
            # Strip numeric resolution markers (3840P/2160P/1080P/720P/...) before the
            # digit/letter spacer below would split "3840P" into "3840 P".
            # Must run before QUALITY_PATTERNS so that removing " 4K " does not glue
            # "SPoRTS" to "3840P" and break the word-boundary anchor.
            for pattern in RESOLUTION_PATTERNS:
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)
            for pattern in QUALITY_PATTERNS:
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Normalize spacing around numbers
        name = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', name)
        name = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', name)

        # Normalize hyphens to spaces
        name = re.sub(r'-', ' ', name)

        # Number-word -> digit (after hyphen normalization, before prefix strip).
        name = NUM_WORDS_RE.sub(lambda m: NUM_WORDS[m.group(0).lower()], name)

        # Dot between LETTERS -> space ("JusticeCentral.TV" -> "JusticeCentral TV",
        # "Racing.com" -> "Racing com"). Restricted to letters on BOTH sides
        # (Channel-Maparr uses \w) so radio frequencies like "97.2"/"102.3" in the
        # CA DB are NOT split into "97 2".
        name = re.sub(r'(?<=[A-Za-z])\.(?=[A-Za-z])', ' ', name)

        # Split CamelCase: "JusticeCentral" -> "Justice Central", "DangerTV" ->
        # "Danger TV". The 4-char floor on the acronym rule protects short brands
        # like "MeTV"/"truTV"/"GameTV" whose existing matches depend on the
        # un-split form. Ported from Channel-Maparr.
        name = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', name)
        name = re.sub(r'([a-z]{4,})([A-Z]{2,})\b', r'\1 \2', name)

        # Remove leading parenthetical prefixes
        while name.lstrip().startswith('('):
            new_name = re.sub(r'^\s*\([^\)]+\)\s*', '', name)
            if new_name == name:
                break
            name = new_name

        # Remove IPTV provider prefixes (enhanced for Lineuparr)
        for pattern in PROVIDER_PREFIX_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Normalize "&" to " and " so "U&YESTERDAY" matches "U and YESTERDAY".
        name = re.sub(r'\s*&\s*', ' and ', name)

        # Apply regional patterns (Pacific/Central/Mountain/Atlantic always stripped when ignore_regional)
        if ignore_regional:
            for pattern in REGIONAL_PATTERNS:
                name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
            for pattern in REGIONAL_EAST_WEST_PATTERNS:
                name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

        if ignore_geographic:
            # Quality bracketed tags like [HD] are handled by QUALITY_PATTERNS.
            # When ignore_quality=False we must not strip them via the geographic
            # bracket pattern (r'\[[A-Z]{2,3}\]'), so skip it in that case.
            _bracket_geo_pattern = r'\[[A-Z]{2,3}\]\s*'
            for pattern in GEOGRAPHIC_PATTERNS:
                if not ignore_quality and pattern == _bracket_geo_pattern:
                    continue
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        if ignore_misc:
            _broad_catchall = r'\s*\([^)]*\)\s*'
            for pattern in MISC_PATTERNS:
                # The broad catch-all "(anything)" pattern would also strip
                # (East)/(West) from lineup names. Skip it when
                # ignore_regional=False so the regional differentiation
                # filter in match_all_streams can still see those markers.
                if pattern == _broad_catchall and not ignore_regional:
                    continue
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Apply user-configured ignored tags
        for tag in user_ignored_tags:
            escaped_tag = re.escape(tag)
            if '[' in tag or ']' in tag or '(' in tag or ')' in tag:
                name = re.sub(escaped_tag + r'\s*', '', name, flags=re.IGNORECASE)
            else:
                if re.match(r'^\w+$', tag):
                    name = re.sub(r'\b' + escaped_tag + r'\b', '', name, flags=re.IGNORECASE)
                else:
                    name = re.sub(escaped_tag + r'\s*', '', name, flags=re.IGNORECASE)

        # Remove callsigns in parentheses
        if ignore_regional:
            name = re.sub(r'\([KW][A-Z]{3}(?:-(?:TV|CD|LP|DT|LD))?\)', '', name, flags=re.IGNORECASE)
        else:
            name = re.sub(r'\([KW](?!EST\)|ACIFIC\)|ENTRAL\)|OUNTAIN\)|TLANTIC\))[A-Z]{3}(?:-(?:TV|CD|LP|DT|LD))?\)', '', name, flags=re.IGNORECASE)

        if ignore_regional:
            name = re.sub(r'\([A-Z0-9]+\)', '', name)

        # Remove common suffixes/prefixes.
        # Network/Channel/TV suffixes are stripped only if ≥2 tokens remain
        # after stripping. Prevents e.g. "Justice Network" → "Justice"
        # (false-matches "Justice Central HD") or "Comedy TV" → "Comedy"
        # (false-matches "Comedy Central"). Alias table handles legitimate
        # collapses like "NHL Network" → "NHL".
        name = re.sub(r'^The\s+', '', name, flags=re.IGNORECASE)
        for _suffix_pattern in (r'\s+Network\s*$', r'\s+Channel\s*$', r'\s+TV\s*$'):
            _stripped = re.sub(_suffix_pattern, '', name, flags=re.IGNORECASE).strip()
            if _stripped and len(_stripped.split()) >= 2:
                name = _stripped

        # Re-apply digit/letter spacing: the tag/paren/callsign removals above can
        # glue a digit to an adjacent token once the parenthetical between them is
        # stripped ("ABC 7 (KGO) SAN" -> "ABC 7SAN"), which breaks US OTA matching
        # (network + OTA-number + (callsign) + city is the dominant US format).
        name = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', name)
        name = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', name)

        # Clean up whitespace
        name = re.sub(r'\s+', ' ', name).strip()

        if not name:
            self.logger.debug(f"normalize_name returned empty for: '{original_name}'")

        return name

    def extract_tags(self, name, user_ignored_tags=None):
        """
        Extract regional indicators, extra tags, and quality tags to preserve them.

        Returns:
            Tuple of (regional, extra_tags, quality_tags)
        """
        if user_ignored_tags is None:
            user_ignored_tags = []

        regional = None
        extra_tags = []
        quality_tags = []

        # Extract regional indicator
        regional_pattern_paren = r'\((East|West)\)'
        regional_match = re.search(regional_pattern_paren, name, re.IGNORECASE)
        if regional_match:
            regional = regional_match.group(1).capitalize()
        else:
            regional_pattern_word = r'\b(East|West)\b(?!.*\b(East|West)\b)'
            regional_match = re.search(regional_pattern_word, name, re.IGNORECASE)
            if regional_match:
                regional = regional_match.group(1).capitalize()

        # Extract ALL tags in parentheses
        paren_tags = re.findall(r'\(([^\)]+)\)', name)
        first_paren_is_prefix = name.strip().startswith('(') if paren_tags else False

        for idx, tag in enumerate(paren_tags):
            # Skip first tag if it is a prefix
            if idx == 0 and first_paren_is_prefix:
                continue

            # Check if tag should be ignored
            if f"({tag})" in user_ignored_tags or f"[{tag}]" in user_ignored_tags:
                continue

            tag_upper = tag.upper()

            # Skip regional indicators
            if tag_upper in ['EAST', 'WEST']:
                continue

            # Skip callsigns
            if re.match(r'^[KW][A-Z]{3}(?:-(?:TV|CD|LP|DT|LD))?$', tag_upper):
                continue

            extra_tags.append(f"({tag})")

        # Extract ALL quality/bracketed tags
        bracketed_tags = re.findall(r'\[([^\]]+)\]', name)
        for tag in bracketed_tags:
            # Check if tag should be ignored
            if f"[{tag}]" in user_ignored_tags or f"({tag})" in user_ignored_tags:
                continue
            quality_tags.append(f"[{tag}]")

        return regional, extra_tags, quality_tags

    def find_best_match(self, query_name, candidate_names, user_ignored_tags=None, remove_cinemax=False):
        """
        Find the best fuzzy match for a name among a list of candidate names.

        Args:
            query_name: Name to match
            candidate_names: List of candidate names to match against
            user_ignored_tags: User-configured tags to ignore
            remove_cinemax: If True, remove "Cinemax" from candidate names

        Returns:
            Tuple of (matched_name, score) or (None, 0) if no match found
        """
        if not candidate_names:
            return None, 0

        if user_ignored_tags is None:
            user_ignored_tags = []

        # Normalize the query (channel name - don't remove Cinemax from it)
        normalized_query = self.normalize_name(query_name, user_ignored_tags)

        if not normalized_query:
            return None, 0

        # Process query for token-sort matching
        processed_query = self.process_string_for_matching(normalized_query)

        best_score = -1.0
        best_match = None

        for candidate in candidate_names:
            # Normalize candidate (stream name) with Cinemax removal if requested
            candidate_normalized = self.normalize_name(candidate, user_ignored_tags)

            # Skip candidates that normalize to empty or very short strings
            if not candidate_normalized or len(candidate_normalized) < 2:
                continue

            processed_candidate = self.process_string_for_matching(candidate_normalized)
            score = self.calculate_similarity(processed_query, processed_candidate)

            if score > best_score:
                best_score = score
                best_match = candidate

        # Convert to percentage and check threshold
        percentage_score = int(best_score * 100)

        if percentage_score >= self.match_threshold:
            return best_match, percentage_score

        return None, 0

    def match_broadcast_channel(self, channel_name):
        """
        Match broadcast (OTA) channel by callsign.

        Args:
            channel_name: Channel name potentially containing a callsign

        Returns:
            Tuple of (callsign, station_data) or (None, None) if no match
        """
        callsign = self.extract_callsign(channel_name)

        if not callsign:
            return None, None

        # Try exact match first
        station = self.channel_lookup.get(callsign)

        if station:
            return callsign, station

        # Try base callsign (without suffix)
        base_callsign = self.normalize_callsign(callsign)
        station = self.channel_lookup.get(base_callsign)

        if station:
            return callsign, station

        return callsign, None

    def get_category_for_channel(self, channel_name, user_ignored_tags=None):
        """
        Get the category for a channel by matching it in the database.

        Args:
            channel_name: Channel name to look up
            user_ignored_tags: User-configured tags to ignore

        Returns:
            Category string or None if not found
        """
        if user_ignored_tags is None:
            user_ignored_tags = []

        # Try broadcast channel first
        callsign, station = self.match_broadcast_channel(channel_name)
        if station:
            return station.get('category')

        # Try premium channel matching
        if self.premium_channels:
            matched_name, score, match_type = self.fuzzy_match(
                channel_name,
                self.premium_channels,
                user_ignored_tags
            )

            if matched_name:
                # Find the full channel object
                for channel_obj in self.premium_channels_full:
                    if channel_obj.get('channel_name') == matched_name:
                        return channel_obj.get('category')

        return None

    def build_final_channel_name(self, base_name, regional, extra_tags, quality_tags):
        """
        Build final channel name with regional indicator, extra tags, and quality tags.
        Format: "Channel Name Regional (Extra) [Quality1] [Quality2] ..."
        """
        parts = [base_name]

        # Add regional indicator WITHOUT parentheses
        if regional:
            parts.append(regional)

        # Add extra tags (already have parentheses)
        if extra_tags:
            parts.extend(extra_tags)

        # Add quality tags (preserve original case and count)
        if quality_tags:
            parts.extend(quality_tags)

        return " ".join(parts)

    def calculate_similarity(self, str1, str2, min_ratio=0.0):
        """Levenshtein similarity ratio (0.0-1.0), defined as 1 - distance/max(len).
        If min_ratio > 0, returns 0.0 early when the result can't reach it.

        bug-026: the ratio MUST be distance/max(len), matching rapidfuzz
        Levenshtein.normalized_similarity. The old (len1+len2-distance)/(len1+len2)
        formula scored higher for the same edit distance and let numbered siblings
        ("Fox Sports 1" vs "2") pass threshold 95. EPG-Janitor ships no rapidfuzz,
        so the pure-Python path ran on every call - this fixes it for both paths.
        """
        if len(str1) == 0 or len(str2) == 0:
            return 0.0

        # Fast path: C-accelerated rapidfuzz when available (same definition).
        if _USE_RAPIDFUZZ:
            # Return the true normalized similarity with NO score_cutoff:
            # rapidfuzz's cutoff rounding zeroes a score landing exactly on
            # min_ratio, but the pure-Python path returns it. Dropping the cutoff
            # makes the two paths agree at the threshold boundary; callers apply
            # their own >= comparison. (rapidfuzz is C-accelerated either way.)
            return _rf_lev.normalized_similarity(str1, str2)

        if len(str1) < len(str2):
            str1, str2 = str2, str1
        len1, len2 = len(str1), len(str2)
        max_len = len1  # the longer string after the swap

        # Length-difference pre-check: minimum possible distance is (len1 - len2),
        # so the max possible ratio is (max_len - (len1 - len2)) / max_len.
        if min_ratio > 0:
            max_possible = (max_len - (len1 - len2)) / max_len
            if max_possible < min_ratio:
                return 0.0

        previous_row = list(range(len2 + 1))
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            # Early termination: a lower bound on the final distance is the current
            # row minimum minus the str1 chars still unprocessed.
            if min_ratio > 0:
                min_distance_so_far = min(current_row)
                remaining = len1 - i - 1
                best_possible_distance = max(0, min_distance_so_far - remaining)
                best_possible_ratio = (max_len - best_possible_distance) / max_len
                if best_possible_ratio < min_ratio:
                    return 0.0
            previous_row = current_row

        distance = previous_row[-1]
        return (max_len - distance) / max_len

    @staticmethod
    def _length_scaled_threshold(base_threshold, shorter_len):
        """Require higher similarity for shorter strings to avoid false positives."""
        if shorter_len <= 4:
            return max(base_threshold, 95)
        elif shorter_len <= 8:
            return max(base_threshold, 90)
        return base_threshold

    @staticmethod
    def _has_token_overlap(str_a, str_b, min_token_len=4, require_majority=False):
        """Check that distinctive tokens are shared between two strings.

        Basic mode: at least one token (>= min_token_len) must be shared.
        Majority mode: uses all meaningful tokens (>= 2 chars, plus single digits),
        requires that more than half of the smaller set overlaps, and applies
        subset/divergent/numeric guards to reject sibling-channel false positives
        even when a fuzzy score is high. Ported from Channel-Maparr; catches:
          - "ABC News" vs "BBC News"            (no shared distinctive token)
          - "Sky Cinema Disney" vs "...Decades" (divergent unique tokens)
          - "In Country Television" vs "Country Music Television" (subset)
          - "BBC One" vs "BBC Two"              (numeric divergence)
        "network"/"channel"/"television" are demoted to common - brand suffixes,
        not distinguishing tokens.
        """
        common_words = {
            "the", "and", "of", "in", "on", "at", "to", "for", "a", "an",
            "network", "channel", "television",
        }

        if require_majority:
            # Single-digit tokens (1,2,...) are channel-distinguishing
            # (BBC 1 vs BBC 2) even though only 1 char, so keep them meaningful.
            def _meaningful(t):
                if t in common_words:
                    return False
                return len(t) >= 2 or t.isdigit()
            tokens_a = {t for t in str_a.split() if _meaningful(t)}
            tokens_b = {t for t in str_b.split() if _meaningful(t)}
            if not tokens_a or not tokens_b:
                return True
            shared = tokens_a & tokens_b
            if not shared:
                return False
            smaller = min(len(tokens_a), len(tokens_b))
            if not len(shared) > smaller / 2:
                return False

            unique_a = tokens_a - tokens_b
            unique_b = tokens_b - tokens_a

            # Subset guard: one side strictly subset AND the larger side has a
            # distinctive (>=5 char) token the smaller lacks -> more specific
            # channel. "In Country Television" vs "Country Music Television".
            # Short extras like "live"/"two" don't trigger this, preserving
            # "ABC News" -> "ABC News Live".
            if not unique_a:
                if any(len(t) >= 5 for t in unique_b):
                    return False
            elif not unique_b:
                if any(len(t) >= 5 for t in unique_a):
                    return False

            # Divergent guard: BOTH sides have unique tokens AND >=1 is a
            # distinctive (>=4 char) word -> different brands.
            # "Sky Cinema Disney" vs "Sky Cinema Decades".
            if unique_a and unique_b:
                if any(len(t) >= 4 for t in unique_a | unique_b):
                    return False

            # Numeric/ordinal divergent guard: BOTH sides have a unique
            # numeric/ordinal token -> sibling channels (BBC One vs BBC Two).
            _NUMERIC = {
                "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve",
                "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
                "first", "second", "third", "fourth", "fifth",
            }
            if (unique_a & _NUMERIC) and (unique_b & _NUMERIC):
                return False

            return True

        # Basic mode: at least one long token shared
        tokens_a = {t for t in str_a.split() if t not in common_words and len(t) >= min_token_len}
        tokens_b = {t for t in str_b.split() if t not in common_words and len(t) >= min_token_len}
        if not tokens_a or not tokens_b:
            return True
        return bool(tokens_a & tokens_b)

    def process_string_for_matching(self, s):
        """Normalize for token-sort matching: lowercase, remove accents, sort tokens."""
        s = unicodedata.normalize('NFD', s)
        s = ''.join(char for char in s if unicodedata.category(char) != 'Mn')
        s = s.lower()
        s = re.sub(r'([a-z])(\d)', r'\1 \2', s)
        cleaned_s = ""
        for char in s:
            if 'a' <= char <= 'z' or '0' <= char <= '9' or char == '+':
                # Preserve '+' — it's a meaningful brand marker
                # (Discovery+, Disney+, Paramount+, Apple TV+, Hulu+).
                cleaned_s += char
            else:
                cleaned_s += ' '
        tokens = sorted([token for token in cleaned_s.split() if token])
        return " ".join(tokens)

    def _channel_number_boost(self, stream_name, expected_number):
        """
        Check if a stream name contains the expected channel number.
        Returns 5-point boost if found, 0 otherwise.
        Only boosts for 3+ digit numbers to avoid false positives on short numbers.
        """
        if expected_number is None:
            return 0
        number_str = str(expected_number)
        # Only boost for 3+ digit numbers (avoids "ESPN2" matching channel 2)
        if len(number_str) < 3:
            return 0
        # Require number to appear with clear delimiters (space, bracket, or string boundary)
        if re.search(r'(?:^|[\s\[\(])' + re.escape(number_str) + r'(?:$|[\s\]\)])', stream_name):
            return 5
        return 0

    @staticmethod
    def _trailing_number(name):
        """Integer value of a space-separated, purely-numeric trailing token,
        or None. 'HBO 2' -> 2, 'ESPN' -> None, 'ESPN2' -> None (digit glued).
        Used to reject 'Foo 1' vs 'Foo 2' false positives. Ported from Channel-Maparr."""
        m = re.search(r'(?:^|\s)(\d{1,4})\s*$', name or "")
        return int(m.group(1)) if m else None

    def alias_match(self, lineup_name, candidate_names, alias_map, user_ignored_tags=None):
        """
        Stage 0: Alias-aware matching.
        For each known alias of the lineup channel name, check if any candidate stream
        name matches after normalization.

        Args:
            lineup_name: Official channel name from lineup JSON
            candidate_names: List of stream names to match against
            alias_map: Dict mapping lineup names to lists of known aliases
            user_ignored_tags: Tags to strip during normalization

        Returns:
            List of (stream_name, score, "alias") tuples for all matches, sorted by score desc.
            Empty list if no alias matches found.
        """
        if not alias_map:
            return []

        if user_ignored_tags is None:
            user_ignored_tags = []

        # Strip the lineup name before dict lookup — channel names in real
        # Dispatcharr data often carry trailing whitespace ("NHL Network "),
        # which was silently missing the alias entry.
        aliases = alias_map.get((lineup_name or "").strip(), [])
        if not aliases:
            return []

        matches = []

        # Normalize all aliases — track spaced and nospace versions separately
        alias_lookup = {}  # normalized_lower -> alias (for exact matching, includes both forms)
        alias_spaced = []  # only the spaced (original) normalized forms (for similarity matching)
        for alias in aliases:
            norm = self.normalize_name(alias, user_ignored_tags)
            if norm:
                norm_lower = norm.lower()
                alias_lookup[norm_lower] = alias
                alias_spaced.append(norm_lower)
                # Also add space-stripped version for exact matching only
                nospace = re.sub(r'[\s&\-]+', '', norm_lower)
                if nospace != norm_lower:
                    alias_lookup[nospace] = alias

        if not alias_lookup:
            return []

        for candidate in candidate_names:
            candidate_lower, candidate_nospace = self._get_cached_norm(candidate, user_ignored_tags)
            if not candidate_lower:
                continue

            # Check exact match against any alias (spaced or nospace)
            if candidate_lower in alias_lookup or candidate_nospace in alias_lookup:
                matches.append((candidate, 100, "alias"))
                continue

            # Check high-similarity match against spaced alias forms only
            best_alias_score = 0
            best_alias_len = 0
            best_alias_norm = ""
            threshold_ratio = self.match_threshold / 100.0
            for norm_alias in alias_spaced:
                ratio = self.calculate_similarity(norm_alias, candidate_lower, min_ratio=threshold_ratio)
                if ratio > best_alias_score:
                    best_alias_score = ratio
                    best_alias_len = min(len(norm_alias), len(candidate_lower))
                    best_alias_norm = norm_alias

            score = int(best_alias_score * 100)
            effective_threshold = self._length_scaled_threshold(self.match_threshold, best_alias_len)

            if score >= effective_threshold and score < 100:
                # Short strings need the stricter majority-overlap guard even
                # at high scores: a 90 score on a 5-char alias is just one
                # Levenshtein substitution ("ME TV" -> "WE tv"), a different
                # channel — and the basic guard passes vacuously when every
                # token is shorter than min_token_len.
                # Always require majority so the subset/divergent/numeric guards run.
                need_majority = True
                if not self._has_token_overlap(best_alias_norm, candidate_lower, require_majority=need_majority):
                    continue

            if score >= effective_threshold:
                matches.append((candidate, score, "alias"))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def fuzzy_match(self, query_name, candidate_names, user_ignored_tags=None,
                    ignore_quality=True, ignore_regional=True, ignore_geographic=True, ignore_misc=True):
        """
        3-stage fuzzy matching: exact → substring → fuzzy token-sort.
        Uses precomputed normalization cache when available for performance.
        (Alias matching is handled separately in alias_match for Lineuparr's pipeline.)

        Returns:
            Tuple of (matched_name, score, match_type) or (None, 0, None)
        """
        if not candidate_names:
            return None, 0, None
        if user_ignored_tags is None:
            user_ignored_tags = []

        normalized_query = self.normalize_name(query_name, user_ignored_tags,
                                               ignore_quality=ignore_quality,
                                               ignore_regional=ignore_regional,
                                               ignore_geographic=ignore_geographic,
                                               ignore_misc=ignore_misc)
        if not normalized_query:
            return None, 0, None

        normalized_query_lower = normalized_query.lower()
        normalized_query_nospace = re.sub(r'[\s&\-]+', '', normalized_query_lower)
        processed_query = None  # Lazy-compute for stage 3

        best_match = None
        best_ratio = 0
        best_match_type = None

        for candidate in candidate_names:
            # Use cache if available, otherwise normalize on the fly
            candidate_lower, candidate_nospace = self._get_cached_norm(candidate, user_ignored_tags)
            if not candidate_lower:
                continue

            # Stage 1: Exact match
            if normalized_query_nospace == candidate_nospace:
                return candidate, 100, "exact"

            ratio = self.calculate_similarity(normalized_query_lower, candidate_lower, min_ratio=0.97)
            if ratio >= 0.97 and ratio > best_ratio:
                best_match = candidate
                best_ratio = ratio
                best_match_type = "exact"
                continue

            # Stage 2: Substring match (only if no exact found yet)
            if not best_match_type or best_match_type != "exact":
                if normalized_query_lower in candidate_lower or candidate_lower in normalized_query_lower:
                    length_ratio = min(len(normalized_query_lower), len(candidate_lower)) / max(len(normalized_query_lower), len(candidate_lower))
                    if length_ratio >= 0.75:
                        sub_ratio = self.calculate_similarity(normalized_query_lower, candidate_lower, min_ratio=self.match_threshold / 100.0)
                        if sub_ratio > best_ratio:
                            sub_score = int(sub_ratio * 100)
                            shorter_len = min(len(normalized_query_lower), len(candidate_lower))
                            effective_threshold = self._length_scaled_threshold(self.match_threshold, shorter_len)
                            need_majority = True
                            if sub_score >= effective_threshold and self._has_token_overlap(normalized_query_lower, candidate_lower, require_majority=need_majority):
                                best_match = candidate
                                best_ratio = sub_ratio
                                best_match_type = "substring"

        # Return exact/substring match if found
        if best_match and best_match_type == "exact":
            return best_match, int(best_ratio * 100), best_match_type
        if best_match and best_match_type == "substring" and int(best_ratio * 100) >= self.match_threshold:
            return best_match, int(best_ratio * 100), best_match_type

        # Stage 3: Fuzzy token-sort matching
        processed_query = self.process_string_for_matching(normalized_query)
        best_score = -1.0
        best_fuzzy = None
        best_fuzzy_proc_candidate = ""

        for candidate in candidate_names:
            processed_candidate = self._get_cached_processed(candidate, user_ignored_tags)
            if not processed_candidate:
                continue

            score = self.calculate_similarity(processed_query, processed_candidate, min_ratio=self.match_threshold / 100.0)
            if score > best_score:
                best_score = score
                best_fuzzy = candidate
                best_fuzzy_proc_candidate = processed_candidate

        percentage_score = int(best_score * 100)
        if percentage_score >= self.match_threshold:
            shorter_len = min(len(processed_query), len(best_fuzzy_proc_candidate))
            effective_threshold = self._length_scaled_threshold(self.match_threshold, shorter_len)
            need_majority = True
            if percentage_score >= effective_threshold and self._has_token_overlap(processed_query, best_fuzzy_proc_candidate, require_majority=need_majority):
                return best_fuzzy, percentage_score, f"fuzzy ({percentage_score})"

        return None, 0, None

    def match_all_streams(self, lineup_name, candidate_names, alias_map, channel_number=None,
                          user_ignored_tags=None, min_score=0):
        """
        Full matching pipeline for Lineuparr: alias → exact → substring → fuzzy, with number boost.
        Returns ALL matching streams sorted by score.

        Args:
            lineup_name: Official channel name from lineup
            candidate_names: List of stream names
            alias_map: Alias dict
            channel_number: Expected channel number for boost
            user_ignored_tags: Tags to strip
            min_score: Minimum score cutoff — results below this are excluded.

        Returns:
            List of (stream_name, score, match_type) tuples sorted by score desc.
        """
        if not candidate_names:
            return []

        if user_ignored_tags is None:
            user_ignored_tags = []

        # Callsign anchor (asymmetric): floor on any-confidence equality;
        # hard-reject only on high-confidence disagreement.
        query_callsign, query_cs_hc = self._extract_callsign_with_confidence(lineup_name or "")
        query_callsign_norm = self.normalize_callsign(query_callsign) if query_callsign else None
        callsign_anchored = set()  # candidate names exempt from region filter

        all_matches = {}  # stream_name -> (score, match_type)

        # Stage 0: Alias matching
        alias_results = self.alias_match(lineup_name, candidate_names, alias_map, user_ignored_tags)
        for stream_name, score, mtype in alias_results:
            if stream_name not in all_matches or score > all_matches[stream_name][0]:
                all_matches[stream_name] = (score, mtype)

        # Stages 1-3: Standard fuzzy matching
        # We need to collect ALL matches above threshold, not just the best
        normalized_query = self.normalize_name(lineup_name, user_ignored_tags)
        if normalized_query:
            normalized_query_lower = normalized_query.lower()
            normalized_query_nospace = re.sub(r'[\s&\-]+', '', normalized_query_lower)
            query_trailing_num = self._trailing_number(normalized_query_lower)
            query_digit_tokens = {t for t in normalized_query_lower.split() if t.isdigit()}
            query_is_shift = bool(_PLUS_SHIFT_RE.search(lineup_name or ""))
            processed_query = self.process_string_for_matching(normalized_query)

            for candidate in candidate_names:
                if candidate in all_matches:
                    continue  # Already matched via alias

                # Use cached normalizations for performance
                candidate_lower, candidate_nospace = self._get_cached_norm(candidate, user_ignored_tags)
                if not candidate_lower:
                    continue

                # Sibling-number guard: "HBO 1" must not match "HBO 2". Only skips
                # when BOTH sides carry a differing trailing number.
                if query_trailing_num is not None:
                    cand_trailing_num = self._trailing_number(candidate_lower)
                    if cand_trailing_num is not None and cand_trailing_num != query_trailing_num:
                        continue

                # Digit-token guard (Stream-Mapparr, EPG-adapted): reject only on
                # genuine number DISAGREEMENT — both sides numbered but sharing no
                # number (a numbered sibling, e.g. "Sky Sports News 13" vs "14").
                # Do NOT reject a numbered channel against an UNnumbered candidate:
                # US OTA channels carry the broadcast number ("ABC 7 (KGO) San
                # Francisco") but the matching EPG entry uses network+market/callsign
                # with no number ("ABC San Francisco"). The trailing-number guard and
                # the token-overlap numeric guard still cover the true sibling cases.
                if query_digit_tokens:
                    cand_digit_tokens = {t for t in candidate_lower.split() if t.isdigit()}
                    if cand_digit_tokens and not (query_digit_tokens & cand_digit_tokens):
                        continue

                # Time-shift guard (Lineuparr): a "+1"/"+2" shift channel must only
                # match shift streams, and vice-versa. Check the ORIGINAL candidate
                # name (normalization alters the "+N" marker).
                if query_is_shift != bool(_PLUS_SHIFT_RE.search(candidate)):
                    continue

                score = 0
                mtype = None

                # Exact
                if normalized_query_nospace == candidate_nospace:
                    score = 100
                    mtype = "exact"
                else:
                    ratio = self.calculate_similarity(normalized_query_lower, candidate_lower, min_ratio=0.97)
                    if ratio >= 0.97:
                        score = int(ratio * 100)
                        mtype = "exact"

                # Substring
                if not mtype:
                    if normalized_query_lower in candidate_lower or candidate_lower in normalized_query_lower:
                        length_ratio = min(len(normalized_query_lower), len(candidate_lower)) / max(len(normalized_query_lower), len(candidate_lower))
                        if length_ratio >= 0.75:
                            ratio = self.calculate_similarity(normalized_query_lower, candidate_lower, min_ratio=self.match_threshold / 100.0)
                            sub_score = int(ratio * 100)
                            shorter_len = min(len(normalized_query_lower), len(candidate_lower))
                            sub_threshold = self._length_scaled_threshold(self.match_threshold, shorter_len)
                            need_majority = True
                            if sub_score >= sub_threshold and self._has_token_overlap(normalized_query_lower, candidate_lower, require_majority=need_majority):
                                score = sub_score
                                mtype = "substring"

                # Fuzzy token-sort
                if not mtype:
                    processed_candidate = self._get_cached_processed(candidate, user_ignored_tags)
                    if processed_candidate:
                        ratio = self.calculate_similarity(processed_query, processed_candidate, min_ratio=self.match_threshold / 100.0)
                        fuzzy_score = int(ratio * 100)
                        shorter_len = min(len(processed_query), len(processed_candidate))
                        fuzzy_threshold = self._length_scaled_threshold(self.match_threshold, shorter_len)
                        need_majority = True
                        if fuzzy_score >= fuzzy_threshold and self._has_token_overlap(processed_query, processed_candidate, require_majority=need_majority):
                            score = fuzzy_score
                            mtype = f"fuzzy ({fuzzy_score})"

                if mtype and score > 0:
                    # Apply channel number boost
                    boost = self._channel_number_boost(candidate, channel_number)
                    all_matches[candidate] = (min(score + boost, 100), mtype)

        # Callsign anchor: a shared callsign rescues an otherwise-unmatched
        # stream; a disagreeing one hard-rejects a false positive. BOTH the
        # floor and the reject require BOTH callsigns to be high-confidence
        # (parenthesized or end-of-name). A loose mid-name word that merely
        # has callsign shape (e.g. "WITH") is not a reliable callsign and
        # must not floor a score at 95 or reject a candidate.
        if query_callsign_norm and query_cs_hc:
            for candidate in candidate_names:
                cand_cs, cand_hc = self._extract_callsign_with_confidence(candidate)
                if not cand_cs or not cand_hc:
                    continue
                if self.normalize_callsign(cand_cs) == query_callsign_norm:
                    existing = all_matches.get(candidate)
                    if existing is None or existing[0] < 95:
                        all_matches[candidate] = (95, "callsign")
                    callsign_anchored.add(candidate)
                else:
                    # High-confidence disagreement -> hard reject.
                    all_matches.pop(candidate, None)

        # Filter out wrong-region matches (East vs West vs Pacific)
        # Detect regional markers from the ORIGINAL lineup name (the normalized
        # form may have stripped them). When present, the lineup is explicitly
        # signaling a zoned feed and we filter candidates to compatible regions
        # regardless of ignore_regional_tags. The toggle only controls whether
        # regionless queries reject Pacific/West candidates.
        original_lower = (lineup_name or "").lower()
        # Detect (e)/(w)/(p) abbreviations in the original name
        _has_abbrev_east = bool(re.search(r'\(\s*e\s*\)', original_lower))
        _has_abbrev_west = bool(re.search(r'\(\s*w\s*\)', original_lower))
        _has_abbrev_pacific = bool(re.search(r'\(\s*p\s*\)', original_lower))
        query_has_east = "east" in original_lower or _has_abbrev_east
        query_has_west = ("west" in original_lower and "western" not in original_lower) or _has_abbrev_west
        query_has_pacific = "pacific" in original_lower or _has_abbrev_pacific

        if query_has_east or query_has_west or query_has_pacific:
            # EXISTING regional-markered branch body, unchanged.
            # Filter candidates to compatible regions.
            filtered = {}
            for stream_name, (score, mtype) in all_matches.items():
                if stream_name in callsign_anchored:
                    filtered[stream_name] = (score, mtype)
                    continue
                sn_lower = stream_name.lower()
                stream_has_east = "east" in sn_lower
                stream_has_west = "west" in sn_lower and "western" not in sn_lower
                stream_has_pacific = "pacific" in sn_lower
                stream_has_region = stream_has_east or stream_has_west or stream_has_pacific

                if query_has_east:
                    # East channel: match East streams or regionless (assume East)
                    if stream_has_west and not stream_has_east:
                        continue  # Skip West-only streams
                    if stream_has_pacific and not stream_has_east:
                        continue  # Skip Pacific-only streams
                elif query_has_west:
                    # West channel: match West or Pacific streams (Pacific is West-coast)
                    if stream_has_east and not stream_has_west and not stream_has_pacific:
                        continue  # Skip East-only streams
                    if not stream_has_region:
                        continue  # Skip regionless streams (they default to East)
                elif query_has_pacific:
                    # Pacific channel: match Pacific OR West streams.
                    # Pacific ≡ West per user spec — "HBO West" and "HBO Pacific"
                    # are the same zoned feed.
                    if stream_has_east and not stream_has_pacific and not stream_has_west:
                        continue  # Skip East-only streams
                    if not stream_has_region:
                        continue  # Skip regionless streams (they default to East)

                filtered[stream_name] = (score, mtype)
            all_matches = filtered

        elif "regional" not in (user_ignored_tags or []):
            # EXISTING regionless-with-filter branch body, unchanged.
            # Prefer regionless EPG entries, reject Pacific/West for regionless queries.
            filtered = {}
            for stream_name, (score, mtype) in all_matches.items():
                if stream_name in callsign_anchored:
                    filtered[stream_name] = (score, mtype)
                    continue
                sn_lower = stream_name.lower()
                stream_has_pacific = "pacific" in sn_lower
                stream_has_west = "west" in sn_lower and "western" not in sn_lower
                if stream_has_pacific or stream_has_west:
                    continue  # Skip Pacific/West for regionless channels (default East)
                filtered[stream_name] = (score, mtype)
            # Only apply filter if it doesn't eliminate all matches
            if filtered:
                all_matches = filtered

        # Deterministic tie-break (Lineuparr): on equal score, prefer the
        # candidate sharing more ORIGINAL-name tokens with the lineup name.
        lineup_tokens = set(re.findall(r'[a-z0-9]+', (lineup_name or "").lower()))

        def _orig_overlap(candidate_name):
            cand_tokens = set(re.findall(r'[a-z0-9]+', candidate_name.lower()))
            return len(lineup_tokens & cand_tokens)

        results = [(name, score, mtype) for name, (score, mtype) in all_matches.items()
                   if score >= min_score]
        results.sort(key=lambda x: (x[1], _orig_overlap(x[0])), reverse=True)
        return results

