"""
Reading a traveller's stay preference out of ordinary chat.

Kept deliberately deterministic (no LLM call): this runs on EVERY chat turn to
decide whether the message is a stay-band request, and paying a model round
trip just to answer "no" would slow down every unrelated message.
"""
import re

# The three bands the planner already prices in enrichments.STAY_BANDS.
BAND_WORDS: dict[str, tuple[str, ...]] = {
    "budget": ("budget", "cheap", "cheapest", "cheaper", "affordable", "low cost",
               "low-cost", "economical", "economy", "backpacker", "hostel"),
    "mid": ("mid range", "mid-range", "midrange", "moderate", "mid tier", "mid-tier",
            "middle", "standard", "3 star", "three star"),
    "premium": ("premium", "luxury", "luxurious", "high end", "high-end", "upscale",
                "5 star", "five star", "4 star", "four star", "posh", "fancy"),
}

BAND_LABELS = {"budget": "budget", "mid": "mid-range", "premium": "premium"}

# The message has to be ABOUT somewhere to sleep. Without this, "we're on a
# tight budget" or "premium trains" would be read as a hotel instruction.
_STAY_WORDS = ("stay", "stays", "staying", "hotel", "hotels", "lodge", "lodges",
               "lodging", "accommodation", "accommodations", "resort", "resorts",
               "guest house", "guesthouse", "homestay", "homestays", "room", "rooms")

_WORD_NUM = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_ALL_WORDS = ("all", "every", "whole", "entire", "everywhere", "throughout",
              "each day", "full trip", "complete")
_NO_WORDS = ("no need", "not needed", "no thanks", "no thank", "nope", "don't",
             "dont", "do not", "leave it", "leave them", "keep it", "keep them",
             "skip", "cancel", "never mind", "nevermind", "as it is", "as is")
_YES_WORDS = ("yes", "yeah", "yep", "sure", "ok", "okay", "please do", "go ahead",
              "do it", "sounds good", "apply", "you decide", "up to you", "book it", "go for it",
              "do that", "sounds great")

# Checked BEFORE consent. "not sure" contains the word "sure", and someone who
# is hedging has not agreed to have every hotel in their plan replaced.
_UNSURE_WORDS = ("not sure", "unsure", "no idea", "dunno", "don't know",
                 "dont know", "do not know", "maybe", "perhaps", "possibly",
                 "i guess", "not decided", "undecided")


def _has_phrase(text: str, phrases: tuple) -> bool:
    """Whole-word phrase match.

    A plain `in` test is wrong here and quietly dangerous: "ok" lives inside
    "looks" and "book", and "sure" inside "not sure" — so substring matching
    read "looks fine", "book it" and "hmm not sure" as consent and went on to
    rewrite every night's hotel. Boundaries make a match mean what it says.
    """
    return any(re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text) for p in phrases)


def detect_stay_band(message: str) -> str | None:
    """The band the traveller is asking about, or None if this isn't a request
    about where to sleep. Both signals are required: a band AND a stay word."""
    text = message.lower().strip()
    if not _has_phrase(text, _STAY_WORDS):
        return None
    # check premium/budget before mid so "mid-range" can't be shadowed
    for band in ("premium", "budget", "mid"):
        if _has_phrase(text, BAND_WORDS[band]):
            return band
    return None


def parse_scope(message: str, nights: list[int]) -> str | list[int] | None:
    """Turn the reply to "whole trip, or which days?" into a scope.

    Returns "all", "none", a LIST of day numbers, or None when the answer
    doesn't settle it (so the caller can ask again rather than guess and change
    the wrong nights).

    A list, not a single day: "days 1 and 2" is an obvious thing to want on a
    four-night trip, and only accepting one day at a time made the traveller
    repeat themselves for every night they cared about.
    """
    text = message.lower().strip()

    # hedging is not agreement — ask again rather than change the wrong nights
    if _has_phrase(text, _UNSURE_WORDS):
        return None

    # "no" first: "no, just day 2" is a day answer, but a bare no is a refusal
    if _has_phrase(text, _NO_WORDS):
        if not re.search(r"\bday\s*\d+|\bonly\b|\bjust\b|\d", text):
            return "none"
    if re.fullmatch(r"\W*(no|nah)\W*", text):
        return "none"

    if _has_phrase(text, _ALL_WORDS):
        return "all"

    days: list[int] = []

    # "day 1", "days 1 and 2", "day 1, 3"
    for m in re.finditer(r"\bdays?\s*((?:\d{1,2}[\s,and&+/-]*)+)", text):
        days += [int(n) for n in re.findall(r"\d{1,2}", m.group(1))]

    # each "day N" written out separately - "day 2 and day 4" is two days,
    # and the grouped pattern above stops at the first one
    for m in re.finditer(r"\bday\s*(\d{1,2})\b", text):
        days.append(int(m.group(1)))

    # "2nd day", "the second day"
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+day\b", text):
        days.append(int(m.group(1)))
    for word, num in _WORD_NUM.items():
        if re.search(rf"\b(?:day\s+{word}|{word}\s+day)\b", text):
            days.append(num)

    # a bare list of numbers ("1 and 2", "1,3") is only safe when every one of
    # them names a real night
    if not days:
        bare = [int(n) for n in re.findall(r"\b\d{1,2}\b", text)]
        if bare and all(b in nights for b in bare):
            days = bare

    if days:
        valid = sorted({d for d in days if d in nights})
        if not valid:
            return None                 # they named nights that don't exist
        return "all" if set(valid) == set(nights) else valid

    # a plain yes to the question means "yes, do it" -> the whole trip
    if _has_phrase(text, _YES_WORDS):
        return "all"

    return None
