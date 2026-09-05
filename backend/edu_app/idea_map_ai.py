"""AI Brainstorm — interactive topic-first argument tree generator.

Runs entirely on TSO's own local topic-knowledge engine — no external AI
API, no network call, no API key. Reuses the exact same deterministic
topic-family database (TOPIC_FAMILIES / GENERIC_FAMILY) and helper
functions (_detect_family, _title_phrase) that already power the offline
essay generator in essay_generator.py, plus the same CEFR-tiered
connector/hedge pools (SAFE_CONNECTORS, HEDGES, CONCLUSION_LINKS) the
rest of TSO Edu already trusts for level-appropriate output — so the
brainstorm tool stays linguistically consistent with the essay generator
and analysis features rather than inventing a parallel vocabulary.

This is a *different* feature from idea_map.py (which draws a structural
diagram from an essay you already wrote), and does not depend on
ai_provider.call_ai(): it starts from just a topic and builds Topic ->
Argument -> Explanation -> Example/Evidence -> Counterargument ->
Rebuttal -> Conclusion using template + database logic.

Knowledge/vocabulary/grammar enrichment in this version:
  - CEFR-aware output: an optional `level` (A1-C2) selects connector
    words, hedging modals, and sentence complexity from the same pools
    essay_generator.py uses, so a B1 map and a C1 map genuinely read
    differently, not just with different topic words.
  - Topic vocabulary is now actually used: each argument branch weaves
    in one of the family's topic-specific vocabulary terms (with a short
    in-line gloss) rather than leaving `family["vocabulary"]" unused.
  - A CEFR synonym-upgrade bank (VOCAB_UPGRADES) swaps a handful of
    plain, overused words (important/good/bad/big/many/help/show/change)
    for level-appropriate alternatives at B2/C1/C2, mirroring the
    writing_coach.db vocabulary_targets table's design one level further.
  - Grammar variety: each sentence role now has 6-8 templates spanning
    different structures (simple present, passive voice, conditional,
    cleft "What X does is...", participle clause, hedged modal) instead
    of 3 near-identical paraphrases, cutting repetition across
    regenerations and giving stronger models to imitate.
  - A short "Angles to consider" list, pulled from the topic family's
    keyword-derived themes, is attached to the topic node's content so
    the student sees the range of angles before drilling into arguments.

Every function here returns plain dicts/lists (JSON-serialisable) built
from validated, length-capped strings — nothing unbounded ever reaches
the client.
"""

import random
import re
import uuid

from .essay_generator import GENERIC_FAMILY, _detect_family, _title_phrase, SAFE_CONNECTORS, HEDGES, _topic_anchor_phrase, _topic_anchor_words
from .writing_coach import normalize_topic, CONCLUSION_LINKS

# ---------------------------------------------------------------------------
# Node types the frontend canvas understands. Keep in sync with the
# NODE_META table in static/brainstorm.js (icon/label per type).
# ---------------------------------------------------------------------------
NODE_TYPES = {
    "topic", "argument", "explanation", "example", "evidence",
    "counterargument", "rebuttal", "conclusion",
}

MAX_TOPIC_LEN = 300
MAX_TITLE_LEN = 120
MAX_CONTENT_LEN = 480

DEFAULT_LEVEL = "B2"
VALID_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}

# ---------------------------------------------------------------------------
# CEFR vocabulary-upgrade bank. Deliberately broader than the bundled
# writing_coach.db vocabulary_targets table (12 rows) so the brainstorm
# tool has good coverage even where the DB table is thin; kept in the same
# word -> {level: alternatives} shape so it could be merged with that table
# later without a redesign. Only touches whole, case-insensitive words at
# a token boundary so it never corrupts topic-specific phrases.
# ---------------------------------------------------------------------------
VOCAB_UPGRADES = {
    "important":  {"B2": ["significant", "considerable"], "C1": ["consequential", "salient"], "C2": ["pivotal", "instrumental"]},
    "good":       {"B2": ["beneficial", "effective"], "C1": ["advantageous", "favourable"], "C2": ["highly advantageous", "markedly beneficial"]},
    "bad":        {"B2": ["harmful", "problematic"], "C1": ["detrimental", "counterproductive"], "C2": ["profoundly detrimental", "deeply counterproductive"]},
    "big":        {"B2": ["considerable", "substantial"], "C1": ["sizeable", "far-reaching"], "C2": ["considerable in scale", "wide-ranging"]},
    "many":       {"B2": ["numerous"], "C1": ["a considerable number of"], "C2": ["a substantial proportion of"]},
    "problem":    {"B2": ["issue", "difficulty"], "C1": ["challenge", "obstacle"], "C2": ["fundamental challenge", "systemic obstacle"]},
}
# Separate bank for words that appear as bare-infinitive VERBS in this
# module's templates (always directly after a hedge like "can"/"may"/"is
# likely to" — see ARGUMENT_OPENERS etc.). Kept apart from the adjective
# bank above so a verb slot is never accidentally filled with a noun
# phrase (e.g. "can upward trend in" is not grammatical, even though
# "upward trend in" is a fine noun-phrase alternative to "increase" in
# other contexts). Every alternative here must itself be a bare-infinitive
# verb or verb phrase so it stays grammatical after "can"/"may"/etc.
VOCAB_VERB_UPGRADES = {
    "help":     {"B2": ["support", "assist"], "C1": ["facilitate"], "C2": ["meaningfully contribute to"]},
    "show":     {"B2": ["demonstrate", "indicate"], "C1": ["illustrate"], "C2": ["bring into sharp relief"]},
    "use":      {"B2": ["make use of", "employ"], "C1": ["utilise"], "C2": ["make effective use of"]},
    "increase": {"B2": ["raise", "boost"], "C1": ["markedly increase"], "C2": ["substantially raise"]},
    "reduce":   {"B2": ["lower", "decrease"], "C1": ["curtail", "diminish"], "C2": ["substantially curtail"]},
    "improve":  {"B2": ["strengthen", "enhance"], "C1": ["meaningfully strengthen"], "C2": ["substantially enhance"]},
}


def _upgrade_vocabulary(text, level):
    """Swap a small set of plain words for CEFR-appropriate alternatives
    at B2 and above. A1/A2/B1 text is left untouched (upgrading vocabulary
    for beginner levels would work against the level, not for it).

    Adjective/noun-type words (VOCAB_UPGRADES) are safe to swap anywhere
    they appear. Verb-type words (VOCAB_VERB_UPGRADES) are only swapped
    when they immediately follow a hedge/modal ("can", "may", "is likely
    to", ...) — i.e. when we can be sure they're sitting in a bare-
    infinitive verb slot — so a noun-phrase-shaped alternative can never
    land somewhere only a verb is grammatical."""
    if level not in {"B2", "C1", "C2"} or not text:
        return text
    rng = random.Random(hash((text, level)) & 0xFFFFFFFF)
    out = text
    for word, tiers in VOCAB_UPGRADES.items():
        alts = tiers.get(level)
        if not alts:
            continue
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", flags=re.IGNORECASE)
        if pattern.search(out):
            out = pattern.sub(lambda m: rng.choice(alts), out, count=1)
    for word, tiers in VOCAB_VERB_UPGRADES.items():
        alts = tiers.get(level)
        if not alts:
            continue
        # Only match this verb directly after a hedge/modal, so the
        # substitution always lands in a genuine bare-infinitive slot.
        pattern = re.compile(
            r"\b(can|may|could|is likely to|can often|in many cases can)\s+" + re.escape(word) + r"\b",
            flags=re.IGNORECASE)
        match = pattern.search(out)
        if match:
            hedge_part = match.group(1)
            out = pattern.sub(lambda m: f"{hedge_part} {rng.choice(alts)}", out, count=1)
    return out


def _connector(level, rng):
    pool = SAFE_CONNECTORS.get(level, SAFE_CONNECTORS[DEFAULT_LEVEL])
    return rng.choice(pool)


def _hedge(level, rng):
    # HEDGES isn't itself CEFR-tiered, but simple hedges ("can", "may")
    # suit lower levels while the fuller phrases suit B2+, so weight the
    # pool by level instead of picking uniformly at every level.
    if level in {"A1", "A2"}:
        pool = ["can", "may"]
    elif level == "B1":
        pool = ["can", "may", "is likely to"]
    else:
        pool = HEDGES
    return rng.choice(pool)


def _conclusion_opener(level, rng):
    pool = CONCLUSION_LINKS.get(level, CONCLUSION_LINKS[DEFAULT_LEVEL])
    return rng.choice(pool)


# ---------------------------------------------------------------------------
# Grammar-varied sentence templates. Each role now spans several distinct
# structures (simple present + hedge, passive voice, conditional, cleft
# "What X does is...", participle clause) rather than 3 near-paraphrases,
# so repeated regeneration on the same topic reads as genuinely different
# writing, not just synonym-shuffled filler. {hedge} and {connector} are
# filled in per-call from the CEFR pools above.
# ---------------------------------------------------------------------------
ARGUMENT_OPENERS = [
    "This {point_cap}, which directly benefits {actor}.",
    "This {hedge} {point}, and the effect on {actor} is usually noticeable quite quickly.",
    "One of the clearest advantages is that {ref} {hedge} {point}.",
    "What this approach does is {point}, which is a genuine benefit for {actor}.",
    "By {gerund_point}, {actor} stand to gain in a fairly direct way.",
    "{connector}, this {hedge} {point}, which is one of the strongest points in its favour.",
]
EXPLANATION_OPENERS = [
    "This matters because it {hedge} {point}.",
    "The underlying reason is that it helps {actor} in a lasting way.",
    "In practice, this happens because {ref} directly affects how {actor} operate day to day.",
    "Put simply, when {ref} is applied consistently, {actor} tend to benefit over time.",
    "This can be explained by the fact that {ref} {hedge} {point}.",
    "Looked at more closely, the reason this works is that it addresses a need {actor} already have.",
]
# Separate templates for CONTEXT-shaped points: family["contexts"] entries
# are already complete standalone clauses (their own subject + verb, e.g.
# "energy policy varies considerably depending on..."), unlike the
# benefit/drawback phrases above which are bare verb phrases. Slotting a
# context clause after a hedge modal ("it {hedge} {point}") produces
# ungrammatical output ("it may energy policy varies..."), so context
# points always get their own templates that treat {point} as a full
# clause rather than a verb continuation.
EXPLANATION_CONTEXT_OPENERS = [
    "This connects to a wider pattern: {point}.",
    "It helps to see this in context — {point}.",
    "More broadly, {point}, which helps explain why this matters here.",
    "This becomes clearer when you consider that {point}.",
]
EXAMPLE_OPENERS = [
    "A clear real-world case is {point}.",
    "A useful illustration of this is {point}.",
    "One concrete example that supports this is {point}.",
    "Consider {point} — a case that makes the point difficult to dispute.",
    "This is well illustrated by {point}.",
]
EVIDENCE_OPENERS = [
    "Cases like this are echoed elsewhere too, since {point}.",
    "This pattern is not an isolated case: {point}.",
    "Wider experience backs this up, as {point}.",
    "Similar outcomes have been observed elsewhere, given that {point}.",
    "This is far from an isolated finding, since {point}.",
]
COUNTERARGUMENT_OPENERS = [
    "This {point_cap}, which is a genuine concern for {actor}.",
    "Critics point out that this can {point}.",
    "Not everyone agrees, mainly because it can {point}.",
    "It could, however, be argued that this can {point}.",
    "A fair objection is that, in some cases, it can {point}.",
    "{connector}, this is not without cost: it can {point}.",
]
REBUTTAL_TEMPLATES = [
    "This concern is fair, but with careful planning the drawback can be managed without losing the overall benefit.",
    "While this is a genuine risk, it does not outweigh the advantages already outlined, provided it is addressed early.",
    "This is worth taking seriously, yet the long-term gains generally justify accepting this manageable cost.",
    "Even so, this risk can largely be mitigated through careful implementation and clear oversight.",
    "This objection has some merit, but it applies mainly in the short term; the longer-term picture looks considerably more positive.",
    "Although this is a legitimate worry, similar concerns have been addressed successfully elsewhere through better planning.",
]
def _topic_phrase_is_plural(topic_phrase):
    """Detect whether a topic phrase needs a plural verb form for correct
    subject-verb agreement in conclusion sentences. Most topic phrases are
    a singular noun phrase ("this policy", "the impact of TikTok on
    teenage sleep") and take a singular verb ("offers", "is"). But a
    genuine two-item comparison topic like "city life and rural life"
    (from a "Compare and contrast X and Y" title) is grammatically
    plural as a combined subject and needs a plural verb ("offer",
    "are") -- using the singular form there ("city life and rural life
    offers...") is a subject-verb agreement error that stood out clearly
    in testing.

    This is deliberately narrow: it only treats the phrase as plural when
    it is a bare "X and Y" pattern (no shared head noun, no single-topic
    wrapper like "the impact of X and Y on Z" where "and" joins two
    causes rather than two whole subjects) -- a false positive here would
    incorrectly pluralise the verb for a genuinely singular topic, which
    is just as much a grammar error as the bug being fixed."""
    if not topic_phrase:
        return False
    # Bare "X and Y" with no other structure -- this is the shape that
    # actually caused the observed bug ("city life and rural life"). If
    # the phrase contains "of", "on", "in", "for" etc. it is almost
    # certainly a single wrapped noun phrase ("the impact of X and Y on
    # Z") where "and" joins something other than the whole subject, so
    # only a plain two-part phrase without those linking prepositions is
    # treated as a plural combined subject.
    if re.search(r'\b(of|on|in|for|to|about|involving|regarding)\b', topic_phrase, flags=re.I):
        return False
    return bool(re.match(r'^[a-z][\w\'-]*(\s+[\w\'-]+){0,3}\s+and\s+[a-z][\w\'-]*(\s+[\w\'-]+){0,3}$', topic_phrase.strip(), flags=re.I))


CONCLUSION_TEMPLATES = [
    "{conclusion_opener} {topic_phrase} bring{plural_s_suffix} clear benefits for {actor}, and the concerns raised can realistically be managed rather than avoided altogether.",
    "{conclusion_opener} the advantages of {topic_phrase} outweigh the drawbacks, provided the risks identified above are addressed directly.",
    "{conclusion_opener} {topic_phrase} offer{plural_s_suffix} real value to {actor}, and a measured approach can limit the downsides while keeping the benefits intact.",
    "{conclusion_opener} while {topic_phrase} {plural_be_verb} not without {plural_possessive} challenges, the overall case in its favour remains the stronger one.",
]


def _clip(value, limit, fallback=""):
    s = str(value if value is not None else fallback).strip()
    return s[:limit]


def _clip_score(value, default=4):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, n))


def _new_id():
    return uuid.uuid4().hex[:8]


def _sentence_case(s):
    s = (s or "").strip()
    return (s[0].upper() + s[1:]) if s else s


def _gerund(point):
    """Present-participle (-ing) form of a benefit/drawback phrase that
    starts with a bare verb ("reduce harmful emissions" -> "reducing
    harmful emissions"), for the participle-clause template.

    English gerund formation is genuinely regular (unlike past tense), so
    this applies the standard spelling rules rather than relying on a
    lookup table: drop a silent trailing -e before adding -ing (e.g.
    "create" -> "creating"), double a final consonant after a single
    stressed vowel in a short verb (e.g. "cut" -> "cutting"), and -ie
    endings become -y before -ing (e.g. "tie" -> "tying", not needed by
    the current database but handled for completeness/future entries).

    A small block-list covers words where -ing exists but wouldn't read
    naturally as the opening of a participle clause here (state verbs
    like "be"/"have"/"need", or a leading word that isn't a verb at all,
    like "not"/"disproportionately"). For those, callers should treat an
    unchanged return as "don't use the participle template for this
    phrase" rather than using the bare form as if it had been converted.
    """
    words = point.split()
    if not words:
        return point
    first = words[0].lower()
    rest = " ".join(words[1:])

    # Words where a gerund form exists but doesn't suit a participle-
    # clause opener here (state/stative verbs, or non-verb leads that
    # occasionally start a phrase in the database).
    skip = {"be", "have", "not", "disproportionately", "need"}
    if first in skip or len(first) < 3:
        return point

    gerund_first = _to_gerund_form(first)
    if gerund_first == first:  # conversion rule didn't fire; stay safe
        return point
    return f"{gerund_first} {rest}".strip()


_GERUND_IRREGULAR_STEMS = {
    # Genuine spelling irregularities the regular rules below don't cover.
    "die": "dying", "lie": "lying", "tie": "tying",
}
_VOWELS = set("aeiou")


def _to_gerund_form(verb):
    """Apply standard English -ing spelling rules to a bare-infinitive
    verb. Returns the verb unchanged if it doesn't look like a simple verb
    this can safely convert (callers treat 'unchanged' as 'don't use it')."""
    if not verb.isalpha():
        return verb
    if verb in _GERUND_IRREGULAR_STEMS:
        return _GERUND_IRREGULAR_STEMS[verb]
    if verb.endswith("ee") or verb.endswith("oe") or verb.endswith("ye"):
        # agree -> agreeing, canoe -> canoeing, dye -> dyeing (keep the e)
        return verb + "ing"
    if verb.endswith("ie"):
        return verb[:-2] + "ying"
    if verb.endswith("e") and not verb.endswith("ee"):
        return verb[:-1] + "ing"
    # Consonant-doubling rule: short, single-syllable verb (single vowel
    # followed by single consonant at the end) doubles the final
    # consonant. e.g. cut -> cutting, plan -> planning. Words ending in
    # an unstressed "-er", "-en", "-on", "-el", "-in" syllable are
    # excluded even when short, since English doesn't double there
    # (lower -> lowering, not "lowerring"; offer -> offering; open ->
    # opening; travel -> traveling) — this is the standard stressed-
    # final-syllable rule, applied via the common unstressed endings
    # rather than a full syllable-stress model (not available offline).
    unstressed_endings = ("er", "en", "on", "el", "in", "or", "ow", "ew", "ay", "ey", "oy")
    # A few real verbs end in one of the "usually unstressed" endings
    # above but are actually stressed on that final syllable, so they DO
    # double (deter -> deterring, refer -> referring, prefer ->
    # preferring, occur -> occurring, begin -> beginning). Spelling alone
    # can't distinguish these from "enter"/"offer"/"open"-type verbs
    # without a pronunciation dictionary, so they're listed explicitly
    # rather than guessed.
    final_stress_exceptions = {"deter", "refer", "prefer", "occur", "begin", "regret", "commit", "admit"}
    if verb in final_stress_exceptions:
        return verb + verb[-1] + "ing"
    if verb.endswith(unstressed_endings):
        return verb + "ing"
    if (len(verb) <= 5 and len(verb) >= 3 and
            verb[-1] not in _VOWELS and verb[-1] not in "wxy" and
            verb[-2] in _VOWELS and (len(verb) < 3 or verb[-3] not in _VOWELS)):
        return verb + verb[-1] + "ing"
    return verb + "ing"


def _fill(template, **kwargs):
    return template.format(**kwargs)


def _normalize_level(level):
    level = str(level or "").strip().upper()
    return level if level in VALID_LEVELS else DEFAULT_LEVEL


def _vocab_gloss_sentence(family, used_vocab, rng):
    """Weave one of the family's topic-specific vocabulary terms into a
    short glossed sentence, e.g. "This connects to the idea of academic
    equity — making sure opportunities are shared fairly." Returns None
    once the family's vocabulary pool is exhausted for this map, so it
    only fires when there's a genuinely fresh term to introduce."""
    pool = family.get("vocabulary") or []
    available = [v for v in pool if v not in used_vocab]
    if not available:
        return None
    term = rng.choice(available)
    used_vocab.add(term)
    glosses = [
        f"This connects to the idea of {term}, a term worth knowing for this topic.",
        f"In IELTS terms, this relates directly to {term}.",
        f"This is closely tied to what is often called {term}.",
    ]
    return rng.choice(glosses)


def _leaf_node(parent_id, node_type, title, content, level=DEFAULT_LEVEL):
    return {
        "id": _new_id(),
        "parentId": parent_id,
        "type": node_type,
        "title": _clip(title, 60),
        "content": _clip(_upgrade_vocabulary(content, level), MAX_CONTENT_LEN),
        "children": [],
        "collapsed": False,
        "strength": None,
        "relevance": None,
    }


def _pick_unique(pool, used, rng):
    """Pick an item from pool that hasn't been used yet this map; falls
    back to the full pool once exhausted so short pools never error out."""
    available = [p for p in pool if p not in used] or list(pool)
    choice = rng.choice(available)
    used.add(choice)
    return choice


def _relevance_score(topic_words, family_keywords, rng):
    """A deterministic-ish strength/relevance score: topics that matched
    more family keywords score higher; small random jitter keeps
    generated maps from feeling identical for near-identical topics."""
    overlap = len(topic_words & family_keywords) if family_keywords else 0
    base = 3 + min(2, overlap)
    return max(3, min(5, base + rng.choice([-1, 0, 0, 1])))


def _argument_template_pool(benefit_point):
    """ARGUMENT_OPENERS, minus the participle-clause ("By {gerund_point},
    ...") template when _gerund() couldn't safely convert this particular
    benefit/drawback phrase — prevents "By require additional funding,
    ..." (bare infinitive left where a gerund was expected) from ever
    being selectable."""
    gerund = _gerund(benefit_point)
    if gerund == benefit_point:
        return [t for t in ARGUMENT_OPENERS if "{gerund_point}" not in t]
    return ARGUMENT_OPENERS


def _build_argument_branch(parent_id, family, actor, ref, benefit_point, rng, used_examples,
                            used_contexts, used_vocab, level, anchor_phrase=''):
    # Use the user's own specific topic wording for this branch's
    # reference about half the time, so the argument tree stays visibly
    # anchored to exactly what the user typed rather than only the
    # matched family's generic subject matter (see _topic_anchor_phrase).
    branch_ref = anchor_phrase if (anchor_phrase and rng.random() < 0.5) else ref
    ref = branch_ref
    connector = _connector(level, rng)
    hedge = _hedge(level, rng)
    template = rng.choice(_argument_template_pool(benefit_point))
    fill_kwargs = dict(point_cap=f"can {benefit_point}", point=benefit_point, actor=actor,
                        ref=ref, hedge=hedge, connector=connector, gerund_point=_gerund(benefit_point))
    arg_content = _fill(template, **fill_kwargs)
    arg_id = _new_id()
    arg_node = {
        "id": arg_id, "parentId": parent_id, "type": "argument",
        "title": _clip(_sentence_case(benefit_point), 60),
        "content": _clip(_upgrade_vocabulary(arg_content, level), MAX_CONTENT_LEN),
        "children": [], "collapsed": False, "strength": None, "relevance": None,
    }

    context_point = _pick_unique(family.get("contexts") or GENERIC_FAMILY["contexts"], used_contexts, rng)
    explanation = _fill(rng.choice(EXPLANATION_OPENERS), point=benefit_point, actor=actor, ref=ref, hedge=hedge)
    vocab_sentence = _vocab_gloss_sentence(family, used_vocab, rng)
    explanation_text = f"{explanation} More broadly, {context_point}."
    if vocab_sentence and rng.random() < 0.6:
        explanation_text = f"{explanation_text} {vocab_sentence}"
    explanation_node = _leaf_node(arg_id, "explanation", "Why?", explanation_text, level)

    example_point = _pick_unique(family.get("examples") or GENERIC_FAMILY["examples"], used_examples, rng)
    example = _fill(rng.choice(EXAMPLE_OPENERS), point=example_point)
    example_node = _leaf_node(arg_id, "example", "Example", example, level)

    evidence_point = _pick_unique(family.get("examples") or GENERIC_FAMILY["examples"], used_examples, rng)
    evidence = _fill(rng.choice(EVIDENCE_OPENERS), point=evidence_point)
    evidence_node = _leaf_node(arg_id, "evidence", "Evidence", evidence, level)

    arg_node["children"] = [explanation_node["id"], example_node["id"], evidence_node["id"]]
    return arg_node, [explanation_node, example_node, evidence_node]


def _angles_for(family):
    """Best-effort 'angles to consider' list derived from the family's own
    vocabulary/keyword data (no extra database dependency) — gives the
    student a quick sense of the range of lenses available on this topic
    before they drill into individual arguments."""
    vocab = family.get("vocabulary") or []
    return vocab[:4]


_CLAUSE_VERB_MARKERS = re.compile(
    r"\b(is|are|was|were|am|be|been|being|has|have|had|do|does|did|"
    r"should|would|could|can|may|might|will|shall|must)\b", re.IGNORECASE)
# A leading first/second-person subject pronoun ("I love...", "we must...",
# "you should...") is a stronger and more general signal that
# _title_phrase's output is a personal statement rather than a formal
# essay-title noun phrase, catching cases the auxiliary/modal list above
# misses (e.g. "I love playing football..." has no auxiliary verb at all,
# just a plain present-tense "love", but is just as unsuitable to slot
# into "exploring {phrase} from both sides").
_PERSONAL_SUBJECT_LEAD = re.compile(r"^\s*(i|we|you|my|our|your)\b", re.IGNORECASE)


def _looks_like_clause(topic_phrase):
    return bool(_CLAUSE_VERB_MARKERS.search(topic_phrase) or _PERSONAL_SUBJECT_LEAD.search(topic_phrase))


def _safe_topic_phrase(topic_phrase):
    """Returns topic_phrase unchanged if it's a genuine noun phrase, or a
    safe generic substitute ("this approach") if it looks like a full
    clause (see _topic_summary_sentence for why) — for use inside
    CONCLUSION_TEMPLATES, which slot topic_phrase into positions that
    require a noun phrase (e.g. "the advantages of {topic_phrase}
    outweigh...")."""
    if _looks_like_clause(topic_phrase):
        return "this approach"
    return topic_phrase


def _topic_summary_sentence(topic_phrase):
    """Wrap _title_phrase()'s output in a summary sentence for the topic
    node. _title_phrase (from essay_generator.py) is designed for formal
    IELTS-style titles (policy questions, "the impact of X") and reliably
    returns a plain noun phrase for those — but for an informal,
    first-person-style topic it can fall back to returning something
    closer to a full clause (e.g. "my favourite hobby is painting
    landscapes"). Slotting a full clause into "exploring {phrase} from
    both sides" reads as broken English, so this detects that case (a
    finite verb already present in the phrase) and uses a safer, more
    generic wrapper instead."""
    if _looks_like_clause(topic_phrase):
        return "An essay exploring this topic from both sides before reaching a balanced conclusion."
    return f"An essay exploring {topic_phrase} from both sides before reaching a balanced conclusion."


def generate_brainstorm_map(topic, advanced=False, level=DEFAULT_LEVEL):
    """Generate a full topic-first argument tree using TSO's own local
    topic-knowledge engine. No network call, no API key. `level` (A1-C2)
    selects CEFR-appropriate connectors, hedges and vocabulary from the
    same pools essay_generator.py already uses. Deterministic inputs
    (same topic) still vary between calls via `random`, matching how the
    offline essay generator behaves."""
    topic = _clip(topic, MAX_TOPIC_LEN)
    if not topic:
        raise ValueError("Topic is required.")
    level = _normalize_level(level)

    rng = random.Random()
    family = _detect_family(topic)
    topic_words = normalize_topic(topic)
    # The specific words from the user's own topic that go beyond the
    # matched family's generic keyword set (e.g. "TikTok", "sleep",
    # "teenagers" for "the impact of TikTok on teenage sleep patterns").
    # Used in place of the plain "it" reference in roughly half of the
    # generated branches so the whole map reads as unmistakably about the
    # user's exact topic, not just the family it was matched to. Also
    # passed into _title_phrase below so a question/clause-style topic
    # (which falls back to a generic "this policy"/"this topic" phrase)
    # still carries the topic's specific content in its very first
    # mention, on the topic-summary node.
    anchor_words = _topic_anchor_words(topic, family)
    anchor_phrase = _topic_anchor_phrase(topic, family)
    topic_phrase = _title_phrase(topic, anchor_words=anchor_words)
    actor = rng.choice(family.get("nouns") or GENERIC_FAMILY["nouns"])
    ref = "it"
    used_vocab = set()

    angles = _angles_for(family)
    angles_line = f" Key angles to consider: {', '.join(angles)}." if angles else ""
    topic_id = _new_id()
    topic_summary = _topic_summary_sentence(topic_phrase)
    topic_node = {
        "id": topic_id, "parentId": None, "type": "topic",
        "title": _clip(topic, MAX_TITLE_LEN),
        "content": _clip(f"{topic_summary}{angles_line}", MAX_CONTENT_LEN),
        "children": [], "collapsed": False, "strength": None, "relevance": None,
    }

    nodes_by_id = {topic_id: topic_node}
    order = [topic_id]

    benefits_pool = list(family.get("benefits") or GENERIC_FAMILY["benefits"])
    num_arguments = 3 if advanced and len(benefits_pool) >= 3 else 2
    used_benefits, used_examples, used_contexts = set(), set(), set()

    for _ in range(num_arguments):
        benefit_point = _pick_unique(benefits_pool, used_benefits, rng)
        arg_node, children = _build_argument_branch(
            topic_id, family, actor, ref, benefit_point, rng,
            used_examples, used_contexts, used_vocab, level, anchor_phrase=anchor_phrase)
        arg_node["strength"] = _relevance_score(topic_words, family.get("keywords") or set(), rng)
        arg_node["relevance"] = _relevance_score(topic_words, family.get("keywords") or set(), rng)
        topic_node["children"].append(arg_node["id"])
        nodes_by_id[arg_node["id"]] = arg_node
        order.append(arg_node["id"])
        for child in children:
            nodes_by_id[child["id"]] = child
            order.append(child["id"])

    connector = _connector(level, rng)
    drawback_point = rng.choice(family.get("drawbacks") or GENERIC_FAMILY["drawbacks"])
    counter_content = _fill(rng.choice(COUNTERARGUMENT_OPENERS), point_cap=f"can {drawback_point}",
                             point=drawback_point, actor=actor, connector=connector)
    counter_node = _leaf_node(topic_id, "counterargument", _sentence_case(drawback_point), counter_content, level)
    topic_node["children"].append(counter_node["id"])
    nodes_by_id[counter_node["id"]] = counter_node
    order.append(counter_node["id"])

    rebuttal_node = _leaf_node(counter_node["id"], "rebuttal", "Rebuttal", rng.choice(REBUTTAL_TEMPLATES), level)
    counter_node["children"].append(rebuttal_node["id"])
    nodes_by_id[rebuttal_node["id"]] = rebuttal_node
    order.append(rebuttal_node["id"])

    _safe_topic_for_conclusion = _safe_topic_phrase(topic_phrase)
    _is_plural = _topic_phrase_is_plural(_safe_topic_for_conclusion)
    conclusion_content = _fill(rng.choice(CONCLUSION_TEMPLATES), topic_phrase=_safe_topic_for_conclusion, actor=actor,
                                conclusion_opener=_conclusion_opener(level, rng),
                                plural_s_suffix="" if _is_plural else "s",
                                plural_be_verb="are" if _is_plural else "is",
                                plural_possessive="their" if _is_plural else "its")
    conclusion_node = _leaf_node(topic_id, "conclusion", "Conclusion", conclusion_content, level)
    topic_node["children"].append(conclusion_node["id"])
    nodes_by_id[conclusion_node["id"]] = conclusion_node
    order.append(conclusion_node["id"])

    return {"topicId": topic_id, "nodes": [nodes_by_id[i] for i in order], "level": level}


# ---------------------------------------------------------------------------
# Single-node regeneration / improvement — also fully local. Re-derives the
# topic family from the stored topic string and re-rolls a fresh point from
# the relevant pool so "Regenerate" produces a genuinely different result.
# ---------------------------------------------------------------------------


def regenerate_node(node_type, topic, context_text, level=DEFAULT_LEVEL):
    node_type = str(node_type or "").strip().lower()
    if node_type not in NODE_TYPES or node_type in {"topic"}:
        raise ValueError("Unsupported node type for regeneration.")
    level = _normalize_level(level)

    rng = random.Random()
    family = _detect_family(topic)
    actor = rng.choice(family.get("nouns") or GENERIC_FAMILY["nouns"])
    anchor_phrase = _topic_anchor_phrase(topic, family)
    ref = anchor_phrase if (anchor_phrase and rng.random() < 0.5) else "it"
    hedge = _hedge(level, rng)
    connector = _connector(level, rng)

    if node_type == "argument":
        point = rng.choice(family.get("benefits") or GENERIC_FAMILY["benefits"])
        content = _fill(rng.choice(_argument_template_pool(point)), point_cap=f"can {point}", point=point, actor=actor,
                         ref=ref, hedge=hedge, connector=connector, gerund_point=_gerund(point))
        return {
            "title": _clip(_sentence_case(point), 60),
            "content": _clip(_upgrade_vocabulary(content, level), MAX_CONTENT_LEN),
            "strength": _clip_score(rng.randint(3, 5)),
            "relevance": _clip_score(rng.randint(3, 5)),
        }
    if node_type == "explanation":
        point = rng.choice(family.get("contexts") or GENERIC_FAMILY["contexts"])
        text = _fill(rng.choice(EXPLANATION_CONTEXT_OPENERS), point=point, actor=actor, ref=ref, hedge=hedge)
        return {"title": "Why?", "content": _clip(_upgrade_vocabulary(text, level), MAX_CONTENT_LEN)}
    if node_type == "example":
        point = rng.choice(family.get("examples") or GENERIC_FAMILY["examples"])
        text = _fill(rng.choice(EXAMPLE_OPENERS), point=point)
        return {"title": "Example", "content": _clip(_upgrade_vocabulary(text, level), MAX_CONTENT_LEN)}
    if node_type == "evidence":
        point = rng.choice(family.get("examples") or GENERIC_FAMILY["examples"])
        text = _fill(rng.choice(EVIDENCE_OPENERS), point=point)
        return {"title": "Evidence", "content": _clip(_upgrade_vocabulary(text, level), MAX_CONTENT_LEN)}
    if node_type == "counterargument":
        point = rng.choice(family.get("drawbacks") or GENERIC_FAMILY["drawbacks"])
        text = _fill(rng.choice(COUNTERARGUMENT_OPENERS), point_cap=f"can {point}", point=point, actor=actor, connector=connector)
        return {
            "title": _clip(_sentence_case(point), 60),
            "content": _clip(_upgrade_vocabulary(text, level), MAX_CONTENT_LEN),
        }
    if node_type == "rebuttal":
        return {"title": "Rebuttal", "content": _clip(_upgrade_vocabulary(rng.choice(REBUTTAL_TEMPLATES), level), MAX_CONTENT_LEN)}
    if node_type == "conclusion":
        topic_phrase = _title_phrase(topic, anchor_words=_topic_anchor_words(topic, family))
        _safe_topic_for_conclusion = _safe_topic_phrase(topic_phrase)
        _is_plural = _topic_phrase_is_plural(_safe_topic_for_conclusion)
        text = _fill(rng.choice(CONCLUSION_TEMPLATES), topic_phrase=_safe_topic_for_conclusion, actor=actor,
                      conclusion_opener=_conclusion_opener(level, rng),
                      plural_s_suffix="" if _is_plural else "s",
                      plural_be_verb="are" if _is_plural else "is",
                      plural_possessive="their" if _is_plural else "its")
        return {"title": "Conclusion", "content": _clip(_upgrade_vocabulary(text, level), MAX_CONTENT_LEN)}
    raise ValueError("Unsupported node type for regeneration.")


def _already_has_strong_verb_after_hedge(text):
    """True if text already has a hedge immediately followed by one of the
    stronger verb-bank alternatives (from any level) — regardless of
    whether *this* function call is what put it there. Guards against
    stacking "can significantly" onto a verb an earlier regenerate/improve
    call already upgraded (e.g. "can substantially curtail"), which the
    naive this-call-only diff can miss once the text has already been
    through a prior upgrade pass."""
    all_alts = set()
    for tiers in VOCAB_VERB_UPGRADES.values():
        for alts in tiers.values():
            all_alts.update(a.lower() for a in alts)
    pattern = re.compile(
        r"\b(can|may|could|is likely to|can often|in many cases can)\s+(" +
        "|".join(re.escape(a) for a in all_alts) + r")\b", flags=re.IGNORECASE)
    return bool(pattern.search(text))


def improve_node(node_type, topic, current_title, current_content, level=DEFAULT_LEVEL):
    """Local 'improve': strengthens phrasing with a CEFR-appropriate
    vocabulary upgrade plus a connective/intensifier pass, rather than a
    full AI rewrite. Keeps the same core claim so the action still feels
    meaningful without needing a network call."""
    level = _normalize_level(level)
    content = (current_content or "").strip()
    if not content:
        content = current_title or ""

    # First pass: swap plain words for stronger CEFR-tiered alternatives.
    # improve_node always upgrades toward at least B2 phrasing, even if
    # the map's own level is lower, since "Improve" is specifically a
    # request for stronger wording.
    upgrade_level = level if level in {"B2", "C1", "C2"} else "B2"
    improved = _upgrade_vocabulary(content, upgrade_level)
    vocab_changed = improved != content
    already_strong = _already_has_strong_verb_after_hedge(improved)

    # Second pass: a connective/intensifier swap. Skipped for "can "
    # specifically when the vocabulary pass already strengthened the verb
    # right after it (e.g. "can markedly increase") — stacking "can
    # significantly markedly increase" would double up the intensifier
    # and read as broken English, so the two passes must not compound.
    intensifiers = [
        ("helps", "clearly helps"),
        ("is likely to", "is highly likely to"),
        ("shows that", "clearly demonstrates that"),
    ]
    if not vocab_changed and not already_strong:
        intensifiers.insert(0, ("can ", "can significantly "))
    intensified = False
    for old, new in intensifiers:
        if old in improved and new not in improved:
            improved = improved.replace(old, new, 1)
            intensified = True
            break
    if not intensified and not vocab_changed and not already_strong:
        # No matched pattern to intensify and no vocabulary change either
        # — prepend a strengthening clause so the action still visibly
        # changes the text.
        improved = f"Importantly, {improved[0].lower()}{improved[1:]}" if improved else improved

    return {"title": _clip(current_title, 60, node_type.capitalize() if node_type else "Node"),
            "content": _clip(improved, MAX_CONTENT_LEN, content)}


def node_to_paragraph(topic, branch_text):
    """Assemble a branch's node lines into one flowing paragraph, fully
    locally. branch_text arrives as newline-separated 'LABEL: content'
    lines (see brainstorm.js branchTextFor); this strips the labels and
    joins the sentences with light connective glue, upgrading vocabulary
    to B2 for a more polished paragraph output."""
    lines = [l.strip() for l in (branch_text or "").splitlines() if l.strip()]
    sentences = []
    for line in lines:
        # Each line looks like "ARGUMENT: Some claim — Some content"
        _, _, rest = line.partition(":")
        rest = rest.strip()
        if not rest:
            continue
        # Drop a leading "Title — " fragment when content was appended
        # after an em dash by branchTextFor, keeping only the content.
        if " — " in rest:
            _, _, rest = rest.partition(" — ")
        rest = rest.strip()
        if rest and rest not in sentences:
            sentences.append(rest)
    if not sentences:
        raise ValueError("Nothing to convert into a paragraph.")
    paragraph = " ".join(sentences)
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    paragraph = _upgrade_vocabulary(paragraph, "B2")
    return _clip(paragraph, 1500)
