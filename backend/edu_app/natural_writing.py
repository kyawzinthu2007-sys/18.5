"""Local TSO Edu Natural Writing Coach.

Deterministic, offline revision assistant. It does not call an AI provider and
is not an AI-detector bypass. It identifies common robotic/formulaic patterns
and proposes meaning-preserving student-voice edits.
"""
import re

PHRASE_REPLACEMENTS = [
    (r"\bin today's rapidly evolving society\b", "today"),
    (r"\bin the modern world\b", "today"),
    (r"\bin this day and age\b", "today"),
    (r"\bit is important to note that\b", ""),
    (r"\bit is worth noting that\b", ""),
    (r"\bplays a crucial role in\b", "helps"),
    (r"\bplays an indispensable role in\b", "is important for"),
    (r"\bhas a significant impact on\b", "affects"),
    (r"\bmake a significant contribution to\b", "help"),
    (r"\bin order to\b", "to"),
    (r"\ba wide range of\b", "many"),
    (r"\ba plethora of\b", "many"),
    (r"\butilize\b", "use"),
    (r"\butilization\b", "use"),
    (r"\bfacilitate\b", "help"),
    (r"\bfacilitating\b", "helping"),
    (r"\bcommence\b", "start"),
    (r"\bendeavour\b", "try"),
    (r"\bendeavors\b", "tries"),
    (r"\bindividuals\b", "people"),
    (r"\bchildren\b", "students"),
    (r"\bapproximately\b", "about"),
    (r"\bnevertheless\b", "however"),
    (r"\bfurthermore\b", "also"),
    (r"\bmoreover\b", "also"),
    (r"\bconsequently\b", "so"),
    (r"\btherefore\b", "so"),
    (r"\bin conclusion\b", "overall"),
]

LEVEL_WORDS = {
    "A2": {"significant": "important", "beneficial": "helpful", "detrimental": "harmful", "subsequently": "later"},
    "B1": {"significant": "important", "facilitate": "help", "subsequently": "later", "numerous": "many"},
    "B2": {"utilize": "use", "facilitate": "help", "numerous": "many"},
}


def _clean_spaces(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()


def _fix_sentence_capitalization(text):
    """Capitalize the first letter after sentence-ending punctuation.

    Needed because phrase removals (e.g. dropping a leading "It is
    important to note that") can leave the next real word lowercase at
    the start of a sentence, producing a grammatically broken result like
    ". we must act now." — this restores standard capitalization without
    touching intentional casing elsewhere in the sentence.
    """
    def cap_after_punct(m):
        return m.group(1) + m.group(2).upper()
    # Start of string, or right after .!? followed by space(s).
    text = re.sub(r"(^\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    text = re.sub(r"([.!?]\s+)([a-z])", cap_after_punct, text)
    return text


def _apply_case(match, replacement):
    original = match.group(0)
    if not replacement:
        return ""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _apply_case_word(original_word, replacement):
    """Like _apply_case, but for a plain word string rather than a regex Match
    (used when substituting a sentence-opening subject pronoun)."""
    if not replacement:
        return ""
    if original_word.isupper():
        return replacement.upper()
    if original_word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def improve(text, level="B2", style="student", language="en"):
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Write a draft before improving it."}
    if language != "en":
        # Keep Myanmar text intact rather than applying unsafe English rules.
        return {"ok": True, "original": text, "improved": text, "changes": [], "note": "Myanmar natural-writing rules are not enabled yet; your text was preserved."}

    out = text
    changes = []
    for pattern, replacement in PHRASE_REPLACEMENTS:
        regex = re.compile(pattern, re.I)
        def repl(m):
            new = _apply_case(m, replacement)
            if m.group(0).strip() and new.strip() and m.group(0).lower() != new.lower():
                changes.append({"type": "phrase", "from": m.group(0), "to": new, "reason": "More natural and concise student wording."})
            elif m.group(0).strip() and not new.strip():
                changes.append({"type": "phrase", "from": m.group(0), "to": "(removed)", "reason": "Removes unnecessary formulaic wording."})
            return new
        out = regex.sub(repl, out)

    selected = LEVEL_WORDS.get(str(level).upper(), LEVEL_WORDS["B2"])
    for old, new in selected.items():
        regex = re.compile(r"\b" + re.escape(old) + r"\b", re.I)
        def repl2(m, old=old, new=new):
            nv = _apply_case(m, new)
            changes.append({"type": "vocabulary", "from": m.group(0), "to": nv, "reason": f"Fits a {level.upper()} student level more naturally."})
            return nv
        out = regex.sub(repl2, out)

    # Reduce repeated sentence-openers only when adjacent sentences use the
    # same opener. Transition words (however/therefore/moreover) can simply
    # be dropped — the sentence still stands without them. Subject pronouns
    # like "this/these/there" CANNOT be dropped (they're the sentence's
    # grammatical subject), so those get swapped for a natural substitute
    # instead of being deleted outright.
    DROPPABLE_OPENERS = {"however", "therefore", "moreover"}
    SUBJECT_SUBSTITUTES = {"this": "it", "these": "they", "there": "it"}
    sentences = re.split(r"(?<=[.!?])\s+", out)
    for i in range(1, len(sentences)):
        if len(sentences[i-1].split()) > 5 and len(sentences[i].split()) > 5:
            # Strip trailing punctuation (commas after "However," etc.) as
            # well as quotes so the opener word compares cleanly.
            a = sentences[i-1].split()[0].lower().strip('"\',.;:')
            b_word = sentences[i].split()[0]
            b = b_word.strip('"\',.;:').lower()
            b_word_clean = b_word.strip('"\',.;:')
            if a != b:
                continue
            if a in DROPPABLE_OPENERS:
                sentences[i] = re.sub(r"^\s*" + re.escape(b_word_clean) + r"[,]?\s*", "", sentences[i], count=1)
                changes.append({"type": "sentence", "from": a, "to": "varied opening", "reason": "Avoids repetitive sentence openings."})
            elif a in SUBJECT_SUBSTITUTES:
                substitute = _apply_case_word(b_word, SUBJECT_SUBSTITUTES[a])
                sentences[i] = re.sub(r"^\s*" + re.escape(b_word), substitute, sentences[i], count=1)
                changes.append({"type": "sentence", "from": a, "to": substitute.lower(), "reason": "Avoids repetitive sentence openings while keeping the sentence's subject."})
    out = _clean_spaces(" ".join(sentences))
    out = _fix_sentence_capitalization(out)

    # Deduplicate repeated changes while retaining order.
    seen = set(); unique = []
    for c in changes:
        key = (c["type"], c["from"].lower(), c["to"].lower())
        if key not in seen:
            seen.add(key); unique.append(c)
    changes = unique[:30]
    return {
        "ok": True,
        "original": text,
        "improved": out,
        "changes": changes,
        "changeCount": len(changes),
        "method": "TSO Edu Local Natural Writing Engine",
        "academic_integrity": "Use the revision as a learning aid and review every change so the final work reflects your own ideas and voice."
    }
