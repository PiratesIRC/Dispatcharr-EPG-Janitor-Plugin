"""
Fuzzy Matcher Module for Lineuparr
Forked from Stream-Mapparr's fuzzy_matcher.py (v26.018.0100) with enhancements:
  - Stage 0: Alias-aware matching
  - Channel number boost for tiebreaking
  - Enhanced provider prefix normalization
"""

import re
import logging
import unicodedata

__version__ = "1.0.0"

LOGGER = logging.getLogger("plugins.lineuparr.fuzzy_matcher")
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
    # EPG-Janitor legacy: bare "US " / "USA " at word boundary
    r'\bUSA?:\s',
    r'\bUSA?\s',
]

PROVIDER_PREFIX_PATTERNS = [
    r'^(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*[:\-\|]\s*',
    r'^\s*\((?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\)\s*',
    r'\s*\|\s*(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*$',
]

MISC_PATTERNS = [
    # Single-letter parenthesized tags: (A), (B), (C)
    r'\s*\([A-Z]\)\s*',
    # Cinemax/specialty
    r'\s*\(CX\)\s*',
    # Any remaining parenthesized group (broad Lineuparr-style fallback)
    r'\s*\([^)]*\)\s*',
]


class FuzzyMatcher:
    """Handles fuzzy matching for Lineuparr with alias support and channel number boosting."""

    def __init__(self, match_threshold=80, logger=None):
        self.match_threshold = match_threshold
        self.logger = logger or LOGGER
        # Cache for pre-normalized stream names (performance optimization)
        self._norm_cache = {}  # raw_name -> normalized_lower
        self._norm_nospace_cache = {}  # raw_name -> normalized_nospace
        self._processed_cache = {}  # raw_name -> processed_for_matching

    def precompute_normalizations(self, names, user_ignored_tags=None):
        """
        Pre-normalize a list of names and cache the results.
        Dramatically improves performance by avoiding redundant normalization
        when matching many lineup channels against the same stream list.
        """
        self._norm_cache.clear()
        self._norm_nospace_cache.clear()
        self._processed_cache.clear()

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

    def normalize_name(self, name, user_ignored_tags=None, ignore_quality=True, ignore_regional=True,
                       ignore_geographic=True, ignore_misc=True):
        """
        Normalize channel or stream name for matching by removing tags, prefixes, and noise.
        """
        if user_ignored_tags is None:
            user_ignored_tags = []

        original_name = name

        # Quality patterns FIRST (before space normalization)
        if ignore_quality:
            for pattern in QUALITY_PATTERNS:
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Normalize spacing around numbers
        name = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', name)
        name = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', name)

        # Normalize hyphens to spaces
        name = re.sub(r'-', ' ', name)

        # Remove leading parenthetical prefixes
        while name.lstrip().startswith('('):
            new_name = re.sub(r'^\s*\([^\)]+\)\s*', '', name)
            if new_name == name:
                break
            name = new_name

        # Remove IPTV provider prefixes (enhanced for Lineuparr)
        for pattern in PROVIDER_PREFIX_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Apply regional patterns (Pacific/Central/Mountain/Atlantic always stripped when ignore_regional)
        if ignore_regional:
            for pattern in REGIONAL_PATTERNS:
                name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
            for pattern in REGIONAL_EAST_WEST_PATTERNS:
                name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

        if ignore_geographic:
            for pattern in GEOGRAPHIC_PATTERNS:
                name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        if ignore_misc and ignore_regional:
            for pattern in MISC_PATTERNS:
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

        # Remove common suffixes/prefixes
        name = re.sub(r'^The\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+Network\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+Channel\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+TV\s*$', '', name, flags=re.IGNORECASE)

        # Clean up whitespace
        name = re.sub(r'\s+', ' ', name).strip()

        if not name:
            self.logger.debug(f"normalize_name returned empty for: '{original_name}'")

        return name

    def calculate_similarity(self, str1, str2, min_ratio=0.0):
        """Levenshtein distance-based similarity ratio (0.0 to 1.0).
        If min_ratio > 0, returns 0.0 early when the result can't reach it."""
        if len(str1) < len(str2):
            str1, str2 = str2, str1
        len1, len2 = len(str1), len(str2)
        if len2 == 0 or len1 == 0:
            return 0.0

        total_len = len1 + len2
        # Length-difference pre-check: even with 0 substitutions, the distance
        # is at least (len1 - len2), so the max possible ratio is bounded.
        if min_ratio > 0:
            max_possible = (total_len - (len1 - len2)) / total_len
            if max_possible < min_ratio:
                return 0.0
            # Max allowed distance to still meet min_ratio
            max_distance = int(total_len * (1.0 - min_ratio))

        previous_row = list(range(len2 + 1))
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            # Early termination: if the minimum value in this row already
            # exceeds max_distance, no subsequent row can produce a valid result
            if min_ratio > 0 and min(current_row) > max_distance:
                return 0.0
            previous_row = current_row

        distance = previous_row[-1]
        return (total_len - distance) / total_len

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
        Majority mode: uses all tokens (>= 2 chars) and requires that more than
        half of the smaller set overlaps. Catches false positives like
        "america racing" vs "america bbc" while allowing single-token matches.
        """
        common_words = {"the", "and", "of", "in", "on", "at", "to", "for", "a", "an"}

        if require_majority:
            # Use all meaningful tokens (>= 2 chars) for stricter checking
            tokens_a = {t for t in str_a.split() if t not in common_words and len(t) >= 2}
            tokens_b = {t for t in str_b.split() if t not in common_words and len(t) >= 2}
            if not tokens_a or not tokens_b:
                return True
            shared = tokens_a & tokens_b
            if not shared:
                return False
            smaller = min(len(tokens_a), len(tokens_b))
            return len(shared) > smaller / 2

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
            if 'a' <= char <= 'z' or '0' <= char <= '9':
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
        if user_ignored_tags is None:
            user_ignored_tags = []

        aliases = alias_map.get(lineup_name, [])
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
                need_majority = score < 90
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
        best_match_candidate_lower = ""

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
                best_match_candidate_lower = candidate_lower
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
                            need_majority = sub_score < 90
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
            need_majority = percentage_score < 90
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
            processed_query = self.process_string_for_matching(normalized_query)

            for candidate in candidate_names:
                if candidate in all_matches:
                    continue  # Already matched via alias

                # Use cached normalizations for performance
                candidate_lower, candidate_nospace = self._get_cached_norm(candidate, user_ignored_tags)
                if not candidate_lower:
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
                            need_majority = sub_score < 90
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
                        need_majority = fuzzy_score < 90
                        if fuzzy_score >= fuzzy_threshold and self._has_token_overlap(processed_query, processed_candidate, require_majority=need_majority):
                            score = fuzzy_score
                            mtype = f"fuzzy ({fuzzy_score})"

                if mtype and score > 0:
                    # Apply channel number boost
                    boost = self._channel_number_boost(candidate, channel_number)
                    all_matches[candidate] = (min(score + boost, 100), mtype)

        # Filter out wrong-region matches (East vs West vs Pacific)
        # Skipped when the user has asked us to ignore regional tags — in that
        # mode the normalization already stripped East/West, so filtering here
        # would be redundant and may incorrectly exclude legitimate matches.
        skip_regional_filter = "regional" in (user_ignored_tags or [])
        if not skip_regional_filter:
            # Check both normalized query AND original name for regional indicators.
            # normalize_name strips East/West/Pacific and parentheticals like (E)/(W)
            # before we get here, so we must detect regional indicators from the
            # original name as well.
            query_lower = (normalized_query or "").lower()
            original_lower = (lineup_name or "").lower()
            # Detect (e)/(w)/(p) abbreviations in the original name
            _has_abbrev_east = bool(re.search(r'\(\s*e\s*\)', original_lower))
            _has_abbrev_west = bool(re.search(r'\(\s*w\s*\)', original_lower))
            _has_abbrev_pacific = bool(re.search(r'\(\s*p\s*\)', original_lower))
            query_has_east = "east" in query_lower or "east" in original_lower or _has_abbrev_east
            query_has_west = (("west" in query_lower and "western" not in query_lower) or
                              ("west" in original_lower and "western" not in original_lower)) or _has_abbrev_west
            query_has_pacific = "pacific" in query_lower or "pacific" in original_lower or _has_abbrev_pacific

            if query_has_east or query_has_west or query_has_pacific:
                filtered = {}
                for stream_name, (score, mtype) in all_matches.items():
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
                        # Pacific channel: only match Pacific streams
                        if stream_has_east and not stream_has_pacific:
                            continue  # Skip East-only streams
                        if stream_has_west and not stream_has_pacific:
                            continue  # Skip West-only streams
                        if not stream_has_region:
                            continue  # Skip regionless streams (they default to East)

                    filtered[stream_name] = (score, mtype)
                all_matches = filtered

            else:
                # Regionless channel: prefer regionless EPG entries, reject Pacific/West
                filtered = {}
                for stream_name, (score, mtype) in all_matches.items():
                    sn_lower = stream_name.lower()
                    stream_has_pacific = "pacific" in sn_lower
                    stream_has_west = "west" in sn_lower and "western" not in sn_lower
                    if stream_has_pacific or stream_has_west:
                        continue  # Skip Pacific/West for regionless channels (default East)
                    filtered[stream_name] = (score, mtype)
                # Only apply filter if it doesn't eliminate all matches
                if filtered:
                    all_matches = filtered

        # Convert to sorted list, filter by min_score, and return
        results = [(name, score, mtype) for name, (score, mtype) in all_matches.items()
                   if score >= min_score]
        results.sort(key=lambda x: x[1], reverse=True)
        return results

