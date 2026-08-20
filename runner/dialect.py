"""Translating other engines' syntax into Python `re`, or declining to.

The cross-population screen runs every pattern through CPython's `re`. That
is not the engine most of these patterns were written for: the production
corpus spans eight registries, and its Perl, Ruby and PHP patterns use
constructs `re` rejects outright. Dropping what will not compile is the
honest default, but it is not free -- it removes patterns non-uniformly
across populations, and the constructs it removes are concentrated in the
anchored validator shapes the matched comparison is built on.

So we also measure what happens when the recoverable part is recovered. Only
rewrites that preserve the language are applied; anything requiring a guess
is declined, and the pattern stays dropped.

Recovered
---------
`\\A`          -> `^`            identical when re.MULTILINE is off, which it is
`\\z`          -> `\\Z`           Python's `\\Z` is Perl's `\\z`: end of string, no
                                newline exception
`\\Z` (Perl)   -> `(?=\\n?\\Z)`    Perl's `\\Z` allows one trailing newline
`\\Q...\\E`    -> `re.escape`    literal span
`\\h` / `\\H`  -> `[ \\t]` / `[^ \\t]`
`(?<name>`    -> `(?P<name>`    Python spells named groups differently
`\\x{HH..}`    -> `\\uXXXX`       Perl's braced code point
`\\e`          -> `\\x1b`

Declined
--------
`\\G`              anchors to the end of the previous match; `re` has no
                   equivalent and no rewrite preserves it.
`\\p{...}`         Unicode properties. `re` has none, and approximating a
                   property with a class would change the language.
`(?i)` mid-pattern Python 3.11 requires global flags at the start, and
                   hoisting one changes what it applies to.
`$var`, `${...}`   interpolation left in place by static extraction. These
                   are template fragments, not regular expressions.
"""

from __future__ import annotations

import re

__all__ = ["to_python", "ANCHOR_START", "ANCHOR_END", "is_anchored"]

# Constructs with no language-preserving rewrite. A pattern carrying one is
# left alone, so it fails to compile and is dropped exactly as before.
_DECLINED = re.compile(
    r"""(?<!\\)\\(?:\\\\)*         # an odd number of backslashes, i.e. a real escape
        (?:G|p\{|P\{)              # \G, \p{...}, \P{...}
      | \(\?[a-zA-Z]*\)            # inline flag group anywhere
      | \$\{                       # ${...} interpolation
    """,
    re.X,
)

_QE = re.compile(r"\\Q(.*?)(?:\\E|\Z)", re.S)
_XBRACE = re.compile(r"\\x\{([0-9A-Fa-f]+)\}")
_NAMED = re.compile(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>")

# `\A` and friends only mean what they mean outside a character class and when
# not themselves escaped. Splitting on class boundaries is more machinery than
# this needs: an odd-backslash lookbehind covers the escaping question, and a
# `\A` inside `[...]` is a syntax oddity we would rather decline than guess at.
def _sub_escape(pattern: str, letter: str, replacement: str) -> str:
    return re.sub(r"(?<!\\)((?:\\\\)*)\\" + letter, r"\1" + replacement, pattern)


def to_python(pattern: str) -> str | None:
    """Rewrite `pattern` into Python `re` syntax, or return None if declined.

    Returns the pattern unchanged when nothing needed rewriting. Returns None
    when it carries a construct we will not guess at, or when the rewrite
    still does not compile.
    """
    if _DECLINED.search(pattern):
        return None

    out = _QE.sub(lambda m: re.escape(m.group(1)), pattern)
    out = _XBRACE.sub(
        lambda m: ("\\u%04x" % int(m.group(1), 16)) if int(m.group(1), 16) <= 0xFFFF
        else ("\\U%08x" % int(m.group(1), 16)),
        out,
    )
    out = _NAMED.sub(r"(?P<\1>", out)
    # Order matters: Perl's `\Z` becomes a lookahead containing `\Z`, so it has
    # to be rewritten before `\z` is turned into `\Z`.
    out = _sub_escape(out, "Z", r"(?=\\n?\\Z)")
    out = _sub_escape(out, "z", r"\\Z")
    out = _sub_escape(out, "A", "^")
    out = _sub_escape(out, "h", "[ \\\\t]")
    out = _sub_escape(out, "H", "[^ \\\\t]")
    out = _sub_escape(out, "e", r"\\x1b")

    try:
        re.compile(out)
    except Exception:
        return None
    return out


# Anchoring, for the task-mix control. The baseline screen tests the literal
# text `^...$`; once `\A`/`\z` have been rewritten the same patterns end in
# `\Z` or a lookahead, so the predicate has to recognise those too or the
# normalised population would look systematically less anchored than the raw
# one for no reason but notation.
ANCHOR_START = re.compile(r"^\^")
ANCHOR_END = re.compile(r"(?:\$|\\Z|\(\?=\\n\?\\Z\))$")


def is_anchored(pattern: str) -> bool:
    return bool(ANCHOR_START.search(pattern) and ANCHOR_END.search(pattern))


def _report():
    """What the compile filter removes from the production corpus, and why.

    Run as `python3 runner/dialect.py`. Compiling half a million patterns is
    seconds; no screening happens here, so this is cheap enough to re-run
    whenever the normaliser changes. Writes results/dialect_drop.json.
    """
    import json
    import sys
    from collections import Counter
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    import config

    config.require_corpora()
    anchored = re.compile(r"^\^.*\$$", re.S)
    perl_anchored = re.compile(r"^\\A.*\\[zZ]$", re.S)
    causes = Counter()
    kept = dropped = kept_anchored = dropped_anchored = recovered = 0
    # Registry counts overlap -- a pattern can appear in several -- so the
    # number of patterns targeting a linear-time engine is not the sum of the
    # two registry totals. What the backtracking-only robustness run actually
    # removes is the patterns that appear in *no* backtracking registry.
    linear = {"godoc", "crates.io"}
    linear_any = linear_only = 0

    path = config.LINGUA_FRANCA_DIR / "data" / "production-regexes" / "uniq-regexes-8.json"
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                pattern = json.loads(line).get("pattern")
            except Exception:
                continue
            if not isinstance(pattern, str) or not pattern:
                continue
            registries = set(json.loads(line).get("useCount_registry_to_nModules") or {})
            if registries & linear:
                linear_any += 1
                linear_only += not (registries - linear)
            try:
                re.compile(pattern)
                kept += 1
                kept_anchored += bool(anchored.match(pattern))
                continue
            except Exception:
                pass
            dropped += 1
            dropped_anchored += bool(anchored.match(pattern) or perl_anchored.match(pattern))
            if to_python(pattern) is not None:
                recovered += 1
            elif re.search(r"\\G", pattern):
                causes[r"\G"] += 1
            elif re.search(r"\\[pP]\{", pattern):
                causes[r"\p{...}"] += 1
            elif re.search(r"\(\?[a-zA-Z]+\)", pattern):
                causes["inline flags"] += 1
            elif re.search(r"\$\{|\$[a-zA-Z_]", pattern):
                causes["host-language interpolation"] += 1
            else:
                causes["malformed or truncated by extraction"] += 1

    out = {
        "kept": kept, "dropped": dropped,
        "kept_anchored_pct": round(100 * kept_anchored / kept, 1),
        "dropped_anchored_pct": round(100 * dropped_anchored / dropped, 1),
        "recovered": recovered,
        "recovered_pct": round(100 * recovered / dropped, 1),
        "unrecovered_by_cause": dict(causes.most_common()),
        "linear_engine_any": linear_any,
        "linear_engine_only": linear_only,
    }
    target = config.RESULTS_DIR / "dialect_drop.json"
    target.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"wrote {target}")


if __name__ == "__main__":
    _report()
