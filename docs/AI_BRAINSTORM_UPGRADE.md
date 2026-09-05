# AI Brainstorm — Premium Argument-Building Canvas

## What this is
A new, **fully local** "topic → argument tree" brainstorming panel added
to the TSO Edu essay tool, alongside (not replacing) the existing free
Idea Map. As of this version it makes **no external API calls** — no
Groq, no OpenAI, no network egress, no API key required. Generation runs
entirely on TSO's own deterministic topic-knowledge engine.

**Important distinction:**
- **Idea Map** (existing, unchanged): free, no AI call, draws a diagram
  from an essay you've *already written*.
- **AI Brainstorm** (new): costs Credit, builds an argument tree starting
  from just a *topic*, before any essay exists — Topic → Argument →
  Explanation/Example/Evidence → Counterargument → Rebuttal → Conclusion.
  "AI" here refers to the automated generation experience, not a call to
  an external large language model.

## How the local engine works
`backend/edu_app/idea_map_ai.py` reuses the exact same topic-knowledge
database and helper functions that already power the offline essay
generator in `essay_generator.py`:
- `TOPIC_FAMILIES` / `GENERIC_FAMILY` — 14+ hand-built topic domains
  (education, technology, environment, health, government, crime, media,
  family, tourism, economy, science, culture, sports, housing,
  sustainability), each with keyword-matched detection, benefits,
  drawbacks, concrete examples, real-world contexts, and vocabulary.
- `_detect_family(topic)` — matches the entered topic to the closest
  family by keyword overlap, falling back to `GENERIC_FAMILY` for
  anything unmatched.
- `_title_phrase(topic)` — turns the raw topic into a grammatical noun
  phrase for use inside generated sentences (handles question-style vs.
  statement-style titles, and policy-flavoured topics).
- `normalize_topic` (from `writing_coach.py`) — stopword-filtered
  keyword extraction used for family matching and a lightweight
  strength/relevance score.

On top of that shared database, `idea_map_ai.py` adds its own sentence
templates (argument openers, explanation/example/evidence framing,
counterargument + rebuttal, conclusion) to assemble a full node tree.
`random.Random()` keeps repeated generations for the same topic varied,
the same way the offline essay generator already behaves.

**Regenerate / Improve / Convert-to-paragraph** are also fully local:
- Regenerate re-rolls a fresh point from the same topic-family pool.
- Improve applies a light intensifier pass to the existing wording
  (e.g. "can" → "can significantly", or prepends "Importantly," if no
  pattern matches) rather than a full AI rewrite.
- Paragraph conversion strips node labels from the branch text and joins
  the remaining sentences into one paragraph.

## Where it lives
The live Edu frontend is `backend/edu_app/templates/index.html` +
`backend/edu_app/static/{app.js,style.css}` (served at `/edu/` by the
`edu_bp` blueprint) — **not** `frontend/index.html`, which is a separate
job-board/mail shell that only links out to `/edu/`.

## New files
- `backend/edu_app/idea_map_ai.py` — local argument-tree generator (map
  generation, branch regeneration, node improvement, node→paragraph
  conversion). No external AI client, no network call.
- `backend/edu_app/static/brainstorm.css` — self-contained dark
  "AI Neural Writing Canvas" theme (glow gradients, neural grid, floating
  particles, glassmorphism node cards), scoped under `.brainstorm-panel`
  so it never affects the rest of the (light-themed) page.
- `backend/edu_app/static/brainstorm.js` — the full interactive canvas:
  cinematic generation sequence, skeleton loading, desktop infinite canvas
  (drag/pan/zoom, animated SVG connections, node CRUD, context menus),
  mobile vertical tree, edit/paragraph modals, Build Essay outline.

## New backend routes (all under `/edu/api/brainstorm*`)
| Route | Cost | Purpose |
|---|---|---|
| `POST /edu/api/brainstorm` | 5 Credit | Generate a full map from a topic |
| `POST /edu/api/brainstorm/regenerate` | 1 Credit | Regenerate one node/branch |
| `POST /edu/api/brainstorm/improve` | 1 Credit | Sharpen one node's wording |
| `POST /edu/api/brainstorm/paragraph` | 1 Credit | Convert a branch into a paragraph |

All four mirror the existing `edu_api_analyze_paid` auth/coin pattern
(`spend_coins` / `refund_coins`, creator accounts exempt). Unlike
Analyze/Generate-Essay/Natural-Writing, **guests are not given a free
pass** here — AI Brainstorm always requires a signed-in account, since
every call spends Credit (the Credit cost reflects the premium
interactive experience, not API spend — there is no external API to pay
for anymore).

## Template/nav changes
- `backend/edu_app/templates/index.html`: added the `#brainstormPanel`
  section above the existing `.idea-map-panel` (untouched), a mobile nav
  button, and `<link>`/`<script>` tags for the two new static files.
- `backend/edu_app/static/style.css`: `.edu-mobile-nav` grid updated from
  5 to 6 columns for the new nav button.

## Data model
Each node: `{ id, parentId, type, title, content, children, collapsed,
strength, relevance }`. `type` is one of: `topic`, `argument`,
`explanation`, `example`, `evidence`, `counterargument`, `rebuttal`,
`conclusion`.

## Testing performed
- `idea_map_ai.py`, `app.py`, `essay_generator.py`, and `writing_coach.py`
  all compile cleanly (`py_compile`).
- `generate_brainstorm_map`, `regenerate_node`, `improve_node`, and
  `node_to_paragraph` were exercised directly against the **real,
  unmodified** `essay_generator.py`/`writing_coach.py` modules — no
  mocking needed anymore, since there's no external service to stub out.
- Stress-tested across 6+ topics spanning different topic families, the
  generic fallback (an off-database topic), question-style vs.
  statement-style titles, and advanced (3-argument) mode.
- Verified error paths: empty topic, unsupported node type for
  regeneration, empty branch text for paragraph conversion.
- Caught and fixed a grammar bug during testing: an early version could
  produce doubled trailing phrases (e.g. "...safer for pedestrians for
  drivers") when a database benefit/drawback phrase already ended in its
  own prepositional phrase. Fixed by switching the sentence template to
  a separate "`, which directly benefits {actor}`" clause — the same
  pattern `essay_generator.py`'s own paragraph builder already uses.
- Not yet tested: a live browser session against a running server with a
  real database. Recommend a manual pass in your dev/staging environment
  before shipping: generate a map, try each node action, test on an
  actual mobile viewport, and watch the Network tab for the 5/1-Credit
  spends.

## Note on the earlier Groq-based version
The first version of this feature (and this doc) called
`ai_provider.call_ai()`, which in turn hit a pre-existing bug elsewhere
in the codebase (`call_ai()` referenced a helper, `_groq_request`, that
doesn't exist in `ai_provider.py`) — that was fixed in a prior revision.
This version removes the Groq dependency for AI Brainstorm entirely per
a later request to use only a local engine; the earlier `call_ai` fix in
`ai_provider.py` is still present and still relevant to the app's other
AI features (Visualize, Translate, etc.), which do still call Groq.

## Knowledge / vocabulary / grammar enrichment pass

The local engine was substantially enriched beyond the initial local
rewrite: CEFR-level awareness, wider template variety, and actual use of
data that was previously sitting unused.

**What's new:**
- **CEFR levels (A1–C2)**: `generate_brainstorm_map`, `regenerate_node`,
  and `improve_node` all take an optional `level` argument. It selects
  connectors, hedging modals, and conclusion openers from the same
  `SAFE_CONNECTORS`/`HEDGES`/`CONCLUSION_LINKS` pools `essay_generator.py`
  already uses, so a B1 map and a C1 map genuinely read differently. A
  level selector was added to the frontend form (`brainstorm.js`/`.css`)
  and threaded through the three relevant API calls and routes.
- **Topic vocabulary is now used**: `family["vocabulary"]` (previously
  dead data — the first local version never touched it) now surfaces as
  glossed terms inside explanation nodes ("This connects to the idea of
  educational equity, a term worth knowing for this topic"), and a "Key
  angles to consider" line was added to the topic node.
- **CEFR vocabulary-upgrade bank** (`VOCAB_UPGRADES` /
  `VOCAB_VERB_UPGRADES`): swaps plain, overused words for level-
  appropriate alternatives at B2+. Split into two banks — adjective/noun-
  type words (safe to swap anywhere) and verb-type words (only swapped
  directly after a hedge modal, so a noun-phrase alternative can never
  land in a verb slot).
- **6–8 grammar-varied templates per sentence role** (was 3): passive-
  leaning, conditional, cleft ("What this approach does is..."),
  participle-clause ("By reducing X, Y..."), and connector-led variants,
  instead of near-identical paraphrases.
- **Rule-based gerund formation**: replaced a ~20-word hardcoded lookup
  with real English -ing spelling rules (silent-e drop, consonant
  doubling, stress exceptions), covering 376 of the 425 real benefit/
  drawback phrases in the database; the remaining 49 safely skip the
  participle template rather than guessing wrong.

**Bugs found and fixed during enrichment (each reproduced and re-verified
with automated stress tests, not just spot-checked):**
1. A noun-phrase vocabulary alternative ("upward trend in") landing in a
   verb slot after a hedge ("can upward trend in...").
2. `contexts` pool entries (full standalone clauses) being slotted after
   a hedge modal meant for bare verb phrases ("it may energy policy
   varies..."). Fixed by giving context-shaped points their own template
   set (`EXPLANATION_CONTEXT_OPENERS`) separate from benefit-shaped ones.
3. Double intensifier stacking when "Improve" was clicked on content the
   vocabulary pass had already strengthened, or when clicked twice in a
   row ("can significantly markedly increase..."). Fixed with an
   `_already_has_strong_verb_after_hedge` check that looks at the text
   itself, not just whether the current call changed it.
4. A consonant-doubling bug in gerund formation ("lower" → "lowerring").
   Fixed by excluding common unstressed endings (-er, -en, -on, -el, -in,
   etc.) from the doubling rule, with a small explicit exception list for
   genuine final-stress verbs (deter → deterring, prefer → preferring).
5. Bare infinitives left in the gerund-only "By {gerund_point}..."
   template for the ~12% of database phrases the gerund converter
   couldn't safely handle ("By require additional funding..."). Fixed by
   filtering that template out of the pool whenever `_gerund()` returns
   the phrase unchanged.
6. `_title_phrase()` (from `essay_generator.py`, designed for formal
   IELTS-style titles) returning something close to a full clause for
   informal/personal-statement topics ("my favourite hobby is painting
   landscapes", "I love playing football..."), which broke when slotted
   into noun-phrase positions ("exploring my favourite hobby is painting
   landscapes from both sides", "the advantages of governments should
   invest... outweigh..."). Fixed with `_looks_like_clause()` (detects
   auxiliary/modal verbs or a leading personal pronoun) and safe
   fallback phrasing ("this topic" / "this approach") for the topic-node
   summary and all four `CONCLUSION_TEMPLATES`.

**Testing performed:** a final regression sweep across 2,700 generated
pieces of content — all 6 CEFR levels × 15 topics (including every edge
case found above) × `generate_brainstorm_map`/`regenerate_node`/
`improve_node` (including double-improve, i.e. clicking Improve twice in
a row) — came back with zero flagged issues against a battery of regex
checks for the specific bug patterns found (bad hedge-modal collisions,
duplicated words, double spacing/punctuation, double intensifiers,
tripled letters, bare infinitives after "By"). A separate audit ran
gerund formation against all 425 real benefit/drawback phrases in the
shared database and found zero doubling/spelling errors.

Not yet tested: a live browser session (no network/DB in this sandbox).
