"""Pure, Django-free glob matching for plugin list settings.

Lives outside plugin.py so the offline unittest harness (which prepends
EPG-Janitor/ to sys.path) can import and test it without Dispatcharr/Django.
"""
import fnmatch


def expand_patterns(tokens, available_names, ci_plain):
    """Resolve user tokens (some glob, some literal) against available_names.

    A token containing '*' or '?' is a glob, matched case-insensitively via
    fnmatch.fnmatchcase on lowercased strings. Any other token is a literal:
    case-insensitive when ci_plain is True, else case-sensitive exact.

    Returns (matched_names, unmatched_tokens):
      - matched_names: names matching >=1 token, ordered by
        (lowest matching token index, then original available_names order),
        de-duplicated.
      - unmatched_tokens: tokens that matched no name, in input order.
    """
    avail = list(available_names)
    avail_order = {name: i for i, name in enumerate(avail)}
    matched_idx = {}          # name -> lowest token index that matched it
    matched_token_idx = set()  # token indices that matched >=1 name

    for ti, tok in enumerate(tokens):
        is_glob = ("*" in tok) or ("?" in tok)
        tok_l = tok.lower()
        for name in avail:
            if is_glob:
                hit = fnmatch.fnmatchcase(name.lower(), tok_l)
            elif ci_plain:
                hit = name.lower() == tok_l
            else:
                hit = name == tok
            if hit:
                matched_token_idx.add(ti)
                if name not in matched_idx or ti < matched_idx[name]:
                    matched_idx[name] = ti

    matched_names = sorted(
        matched_idx, key=lambda n: (matched_idx[n], avail_order[n]))
    unmatched_tokens = [t for i, t in enumerate(tokens)
                        if i not in matched_token_idx]
    return matched_names, unmatched_tokens
