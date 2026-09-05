# TSO Edu Grammar Academy — Certificate of Completion (integrated module)

This generates a **Certificate of Completion** for students who finish all
lessons of the TSO Edu Grammar Academy curriculum and pass the Final
Mastery Exam. It is issued and controlled entirely by the backend in
`app.py` — see the routes below.

## What this certificate is, and isn't

- It certifies that a specific student completed TSO Edu's own internal
  curriculum and passed TSO Edu's own internal exam. That's it.
- It is **not** an accredited or externally-recognised academic
  credential. It does not carry weight with universities, employers, or
  any other institution unless that institution independently chooses to
  recognise it — the same way any organization's internal training
  certificate would need outside recognition on its own merits.
- The certificate text should never be changed to imply outside
  accreditation, institutional partnership, or equivalence to a formal
  academic qualification unless that is separately, actually true (e.g. a
  real accreditation agreement is signed).

## How issuance actually works (server-enforced, not client-claimed)

1. A student completes all lessons in `edu_app/grammar_data.py`
   (`GRAMMAR_LESSONS`) — tracked via `/edu/api/grammar/progress`.
2. Once all lessons are marked complete, the student can request the
   **Final Mastery Exam** via `GET /edu/api/grammar/final_exam`, which
   returns two questions per lesson (drawn from each lesson's own
   hand-verified quiz) bound to a short-lived, single-use `examToken`.
   The answer key is never sent to the client.
3. The student submits answers to
   `POST /edu/api/grammar/final_exam/submit`. Grading happens entirely
   server-side against the bound answer key. A score at or above
   `GRAMMAR_CERT_PASS_THRESHOLD` (currently 80%, set in `app.py`) marks
   the exam as passed and is stored in the user's persisted state.
4. `POST /edu/api/grammar/certificate/issue` re-checks eligibility
   server-side (`_grammar_certificate_eligible()`  — all lessons complete
   **and** a passed Final Mastery Exam) before generating anything. A
   client cannot obtain a certificate by claiming completion; eligibility
   is always re-derived from stored progress + exam state.
5. `GET /edu/api/grammar/certificate/download` streams the previously
   issued PDF for that signed-in user.

## Lesson count — never hardcode it

`draw_certificate()` in `make_certificate.py` resolves `lessons_completed`
**live** from `len(GRAMMAR_LESSONS)` unless explicitly overridden. Do not
reintroduce a hardcoded lesson count anywhere in this flow — the
curriculum has already grown once (30 → 64 lessons) and will likely grow
again.

## Required environment variables (production)

- `GRAMMAR_CERT_ISSUE_SECRET` — a real, private secret used to derive the
  tamper-evident verification code. **Certificate issuance will raise a
  clear error and refuse to run without this set** — there is no
  hardcoded fallback, because a shared placeholder secret would make
  every certificate forgeable.
- `GRAMMAR_CERT_VERIFY_URL_BASE` — the real public verification page,
  e.g. `https://your-real-domain.com/verify/`. Defaults to a placeholder
  `tso-edu.example` URL if unset, which is fine for local testing but
  should be set for real issuance.
- `GRAMMAR_CERT_OUTPUT_DIR` — where issued PDFs are written on disk
  (defaults to `edu_app/certificate/_issued/` next to this module).
  On Railway, note this directory is **not persistent across deploys**
  unless backed by a mounted volume — for durability, consider also
  uploading issued PDFs to Supabase storage from the issuance route.

## Still required before this is production-ready

- ✅ ~~Build the actual verification page/endpoint~~ — done. See
  `GET /verify/<cert_id>?code=...` (public HTML page) and
  `GET /edu/api/grammar/certificate/verify?certId=...&code=...` (JSON
  variant) in `app.py`. Both re-derive the verification hash server-side
  from `GRAMMAR_CERT_ISSUE_SECRET` rather than trusting a stored code
  match alone, so a copy with the name/date edited will correctly fail
  even if the code string was copied verbatim.
- ✅ ~~Persist issued-certificate records durably~~ — done. Run
  `mail_migration/021_grammar_certificates.sql` against your **main**
  Supabase project (the one with the `users` table) before issuing any
  real certificates. Without this table, issuance still generates the PDF
  but logs a loud warning, and `/verify/<cert_id>` will report "not
  found" for every certificate since it has nowhere to look them up.
- Set `GRAMMAR_CERT_VERIFY_URL_BASE` to your real domain once deployed,
  e.g. `https://talentshowoff.com/verify/` — the route itself
  (`/verify/<cert_id>`) is already live at whatever domain the app is
  running on; this variable only controls what URL gets *printed on the
  certificate*, so it needs to match.
- Anti-forgery/anti-copy PDF details (guilloché background, seal,
  PDF permission locking, embedded metadata) are unchanged from the
  original design — see `make_certificate.py` for specifics.
- Optional hardening: add an admin-only route to set `revoked = true` on a
  `grammar_certificates` row (e.g. if a certificate is issued in error) —
  the verify page and JSON endpoint already check and render that state,
  but nothing currently sets it.
