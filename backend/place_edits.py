"""
"also include Hampi" / "drop Varkala" — turning that into a changed stop list.

The hard part is the place NAME, not the verb. Rather than trust free-text
parsing, we pull a candidate phrase out with a regex and then match it against
a list we already know: the trip's own stops for a removal, and the
destination's attraction list for an addition. Matching against a known set is
what makes this reliable — and it means an addition arrives with its real
coordinates, category and blurb instead of a bare name.
"""
import difflib
import re

_ADD_VERBS = (
    "add", "include", "also visit", "also see", "also go", "put in", "insert",
    "can we visit", "can we see", "i want to visit", "i want to see", "throw in",
    "squeeze in", "cover",
)
_REMOVE_VERBS = (
    "remove", "drop", "skip", "exclude", "take out", "leave out", "cut",
    "without", "don't want", "dont want", "do not want", "not interested in",
    "no need for", "cancel",
)

# words that follow a place name but aren't part of it
_TRAILING = re.compile(
    r"\b(please|also|too|as well|from the (plan|trip|itinerary)|in the (plan|trip|itinerary)"
    r"|to the (plan|trip|itinerary)|on day \d+|for day \d+|day \d+)\b.*$",
    re.I,
)


# "drop Varkala and add Kovalam" carries two instructions; the name ends where
# the next one begins. Only cut on a following VERB — "Fort Kochi and Marine
# Drive" is one phrase naming two places, not an instruction boundary.
_NEXT_INSTRUCTION = re.compile(
    r"\s+(?:and|then|but|also)\s+(?:add|include|remove|drop|skip|exclude|visit|see)\b.*$",
    re.I,
)


def _clean(name: str) -> str:
    name = _NEXT_INSTRUCTION.sub("", name)
    name = _TRAILING.sub("", name)
    name = name.strip(" \t.,!?;:\"'()")
    # a stray leading article reads badly in a confirmation message
    name = re.sub(r"^(the|a|an)\s+", "", name, flags=re.I)
    return name.strip()


def detect_place_edit(message: str) -> dict | None:
    """`{"action": "add"|"remove", "phrase": str}` or None.

    `phrase` is what the traveller typed, not a resolved place — resolving is
    the caller's job, because only it knows the candidate lists.
    """
    text = message.strip()
    low = text.lower()

    # removal first: "drop Varkala and add Kovalam" is really about the drop,
    # and treating it as an addition would silently keep the unwanted place
    for verbs, action in ((_REMOVE_VERBS, "remove"), (_ADD_VERBS, "add")):
        for verb in verbs:
            m = re.search(rf"(?<!\w){re.escape(verb)}(?!\w)\s+(.+)", low)
            if not m:
                continue
            phrase = _clean(text[m.start(1):])          # keep original casing
            if len(phrase) >= 3:
                return {"action": action, "phrase": phrase}
    return None


def match_place(phrase: str, candidates: list[dict], cutoff: float = 0.62) -> dict | None:
    """The candidate whose name best matches the phrase, or None.

    Deliberately fuzzy — people type "alleppey" for "Alleppey Backwaters" and
    "padmanabhaswamy" for the full temple name — but cut off well short of a
    guess, because removing the wrong place is worse than asking again.
    """
    if not phrase or not candidates:
        return None
    want = phrase.lower().strip()

    # an exact substring match in either direction beats fuzzy scoring
    for c in candidates:
        name = (c.get("name") or "").lower()
        if not name:
            continue
        if want == name or want in name or name in want:
            return c

    best, best_score = None, 0.0
    for c in candidates:
        name = (c.get("name") or "").lower()
        if not name:
            continue
        score = difflib.SequenceMatcher(None, want, name).ratio()
        # also score against the first word or two, so "hampi" matches
        # "Hampi Group of Monuments"
        head = " ".join(name.split()[:2])
        score = max(score, difflib.SequenceMatcher(None, want, head).ratio())
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= cutoff else None
