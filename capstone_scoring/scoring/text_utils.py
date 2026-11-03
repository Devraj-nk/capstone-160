"""
Text helpers that work the same for English, native Indic scripts and
romanized/code-mixed text.

IMPORTANT: we do NOT use regex \\w for tokenizing. In Python, \\w does not match
Indic vowel signs/viramas (Unicode category Mn/Mc), so "ಸಹಾಯ" would be broken
into pieces. We split on whitespace + punctuation instead.
"""
import re
import unicodedata

SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),   # Hindi
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
}
LANG_SCRIPT = {"hi": "devanagari", "kn": "kannada", "ta": "tamil", "te": "telugu", "en": "latin"}

_SPLIT = re.compile(r"[\s\.,!?;:\"'“”‘’()\[\]{}<>…।॥|#@/\\\-–—_*~+=&%$^`]+")
_REPEAT_CHAR = re.compile(r"(.)\1{3,}")        # "helppppp", "!!!!"
_PUNCT_RUN = re.compile(r"[!?]{3,}")


def normalize(text: str) -> str:
    """NFC-normalize, drop zero-width joiners (typed inconsistently in Indic
    keyboards), lowercase (only affects Latin), collapse spaces."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u200c", "").replace("\u200d", "")
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in _SPLIT.split(normalize(text)) if t]


def char_script(ch: str) -> str:
    cp = ord(ch)
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or (0x00C0 <= cp <= 0x024F):
        return "latin"
    for name, (lo, hi) in SCRIPT_RANGES.items():
        if lo <= cp <= hi:
            return name
    if ch.isdecimal():
        return "digit"
    if ch.isspace():
        return "space"
    cat = unicodedata.category(ch)
    if cat.startswith("P") or cat.startswith("S"):
        return "punct"
    return "other"


def script_profile(text: str) -> dict:
    """Fraction of letters in each script (digits/space/punct ignored)."""
    counts = {}
    for ch in text or "":
        s = char_script(ch)
        if s in ("digit", "space", "punct"):
            continue
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()} if total else {}


def has_number(tokens: list[str]) -> bool:
    """True for ASCII and Indic digits alike (०-९, ೦-೯, ௦-௯, ౦-౯)."""
    return any(ch.isdecimal() for t in tokens for ch in t)


def noise_signals(raw_text: str) -> dict:
    text = raw_text or ""
    latin_letters = [c for c in text if c.isascii() and c.isalpha()]
    caps_ratio = (sum(c.isupper() for c in latin_letters) / len(latin_letters)
                  if len(latin_letters) >= 10 else 0.0)
    return {
        "repeat_runs": len(_REPEAT_CHAR.findall(text)),
        "punct_runs": len(_PUNCT_RUN.findall(text)),
        "caps_ratio": caps_ratio,   # only meaningful for Latin; Indic has no case
    }


# ---------------------------------------------------------------------------
# Lexicon matching
# ---------------------------------------------------------------------------
class CompiledLexicon:
    """Compiles one category ({lang_key: [terms]}) into fast matchers."""

    def __init__(self, lang_lists: dict):
        self.exact, self.prefix, self.suffix, self.inner, self.phrases = set(), [], [], [], []
        for terms in lang_lists.values():
            for raw in terms:
                term = normalize(raw)
                if " " in term:
                    # tokenize the phrase exactly like tweets are tokenized, so
                    # "media won't show" and "100% true" line up with tweet tokens
                    open_end = term.endswith("*")
                    phrase = " ".join(tokenize(term.rstrip("*")))
                    self.phrases.append((phrase, open_end, raw))
                elif term.startswith("*") and term.endswith("*"):
                    self.inner.append((term.strip("*"), raw))
                elif term.endswith("*"):
                    self.prefix.append((term[:-1], raw))
                elif term.startswith("*"):
                    self.suffix.append((term[1:], raw))
                else:
                    self.exact.add(term)

    def match(self, tokens: list[str]) -> set[str]:
        """Return the set of DISTINCT lexicon terms found (repeats don't add)."""
        found = set()
        tok_set = set(tokens)
        found |= (self.exact & tok_set)
        for tok in tok_set:
            for stem, raw in self.prefix:
                if tok.startswith(stem):
                    found.add(raw)
            for suf, raw in self.suffix:
                if len(tok) >= len(suf) + 2 and tok.endswith(suf):
                    found.add(raw)
            for piece, raw in self.inner:
                if tok.find(piece) > 0:      # inside the word, not at its start
                    found.add(raw)
        if self.phrases:
            joined = " " + " ".join(tokens) + " "
            for phrase, open_end, raw in self.phrases:
                needle = " " + phrase + ("" if open_end else " ")
                if needle in joined:
                    found.add(raw)
        return found


def saturating_score(hits: int, base: float) -> float:
    """0 hits -> 0, 1 -> 0.6, 2 -> 0.84, 3 -> 0.94 (with base 0.4)."""
    return 1.0 - base ** hits if hits > 0 else 0.0
