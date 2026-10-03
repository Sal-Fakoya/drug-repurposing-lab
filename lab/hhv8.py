"""Classify a record's HHV-8 / KSHV / Kaposi / HIV mentions as positive, negated_only or none.

Idiopathic MCD papers routinely say "HHV-8-negative" to rule out viral MCD, so a plain mention
test would throw away the papers that matter most. A mention counts as negated only when it
is written as one of these forms (a list of terms joined by "/", ",", "and", "or" counts too):

- TERM-negative, TERM negative, TERM-seronegative, TERM seronegative
  ("HHV-8 and HIV negative", "HIV-1-negative", "KSHV)-negative")
- negative for TERM, seronegative for TERM ("negative for HHV-8/HIV",
  "seronegative for both HHV-8 and HIV")

Status: "positive" if any mention is not negated (present or causal), "negated_only" if every
mention is negated, "none" if there is no mention. Anything else, such as "no evidence of
HHV-8" or "HHV-8 PCR was negative", counts as positive: the exclusion run then drops the
record, which errs on the side of removing viral literature.
"""
import re

TERMS = ("HHV-8", "KSHV", "Kaposi", "HIV")
STATUSES = ("positive", "negated_only", "none")

_KSHV = (r"Kaposi'?s?\s+sarcoma[-\s]+associated\s+herpes\s?virus(?:\s*\(\s*KSHV\s*\))?"
         r"|\bKSHV\b")
_HHV8 = (r"\bhuman\s+herpes\s?virus[-\s]*(?:type\s*)?8\b(?:\s*\(\s*(?:HHV[-\s]?8|KSHV)\s*\))?"
         r"|\bHHV[-\s]?8\b")
_KAPOSI = r"\bKaposi"
_HIV = r"\bHIV(?:[-\s]?[12])?\b"
# Named groups decide the term; the long KSHV name is tried before the bare "Kaposi".
_MENTION = re.compile(rf"(?P<KSHV>{_KSHV})|(?P<HHV8>{_HHV8})|(?P<Kaposi>{_KAPOSI})|(?P<HIV>{_HIV})",
                      re.IGNORECASE)
_ANY = rf"(?:{_KSHV}|{_HHV8}|{_KAPOSI}|{_HIV})"
_JOIN = r"\s*(?:/|,|&|\band\b|\bor\b)\s*"
_NEGATED_AFTER = re.compile(
    rf"(?:{_JOIN}{_ANY})*\s*\)?\s*[-\s]?\s*(?:sero)?negativ(?:e|ity)\b", re.IGNORECASE)
_NEGATED_BEFORE = re.compile(
    rf"\b(?:sero)?negative\s+for\s+(?:both\s+|either\s+)?(?:{_ANY}{_JOIN})*$", re.IGNORECASE)
_NAMES = {"KSHV": "KSHV", "HHV8": "HHV-8", "Kaposi": "Kaposi", "HIV": "HIV"}
_LOOKBEHIND = 200  # characters searched before a mention for "negative for ..."


def _negated(text: str, match: re.Match) -> bool:
    if _NEGATED_AFTER.match(text, match.end()):
        return True
    return bool(_NEGATED_BEFORE.search(text[max(0, match.start() - _LOOKBEHIND):match.start()]))


def classify(*texts: str) -> tuple[str, list[str]]:
    """(status, terms): status in STATUSES, terms = every term mentioned, in TERMS order."""
    text = " ".join(t for t in texts if t)
    found, positive = set(), False
    for match in _MENTION.finditer(text):
        found.add(_NAMES[match.lastgroup])
        if not _negated(text, match):
            positive = True
    status = "none" if not found else "positive" if positive else "negated_only"
    return status, [t for t in TERMS if t in found]
