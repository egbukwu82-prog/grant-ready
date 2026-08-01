# GrantReady — Handover Document

_Last updated: 2026-07-30. Covers Phase 1 MVP (matching engine, built July 6) and Phase 2
(crawler + confidence-tier system, built July 9)._

## What this project is

A local web app that lets an Alberta farmer answer a short questionnaire and get back a
ranked, accurately sourced list of grant programs they actually qualify for, drawn from a
hand-compiled dataset of 13 real Alberta/federal programs — plus a crawler that re-checks
each program's official source page and assigns a confidence tier to every program instead
of treating all data as equally fresh.

Governing documents (in repo root):

- `grantready_oneshot_spec.md` — Phase 1 spec (matching engine, questionnaire, UI)
- `grantready_crawler_spec.md` — Phase 2 spec (crawler, confidence tiers, change log)
- `grantready_seed_programs.json` — **the only source of grant facts.** Never invent a
  program, dollar figure, deadline, or eligibility rule that isn't in this file.

## Core principles (non-negotiable)

1. **No invented grant facts.** The seed JSON is ground truth; the code only reads it.
2. **Detect and flag, never silently resolve.** The crawler never overwrites a stored
   fact. Every detected discrepancy becomes a `pending_review` change-log entry for a
   human to confirm or reject. A crawler that quietly "corrects" a deadline is worse than
   no crawler.
3. **No invisible uncertainty.** Seed-level conflicts (`flag` fields, OFCAF's `FLAG:`
   deadline) and crawler confidence tiers are both surfaced in the UI, as distinct badges.

## Repository layout

```
grantready/
├── grantready_seed_programs.json   # source of truth; crawler adds tier/timestamp/change_log fields
├── grantready_oneshot_spec.md      # Phase 1 spec
├── grantready_crawler_spec.md      # Phase 2 spec
├── crawler_history.db              # SQLite: snapshots + append-only change log (gitignored)
├── backend/
│   ├── .venv/                      # Python 3.9 venv (fastapi, uvicorn, anthropic, httpx)
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI app, /api/health /api/programs /api/match (port 8001)
│   │   ├── models.py               # Pydantic: QuestionnaireAnswers, ProgramMatch, MatchResponse
│   │   ├── matching.py             # two-layer matching + urgency tiering + funding plain-language
│   │   ├── blurbs.py               # template draft-application blurbs (LLM upgrade optional)
│   │   └── repository.py           # ProgramRepository ABC + JsonFileProgramRepository (read + write)
│   └── crawler/
│       ├── sources.py              # generic Source: URL → text + status + timestamp + sha256 hash
│       ├── differ.py               # LLM field diff (if ANTHROPIC_API_KEY) or hash diff fallback
│       ├── history.py              # CrawlHistoryRepository ABC + SQLite impl (snapshots, change_log)
│       └── run.py                  # CLI entry: python -m crawler.run  (also tier assignment logic)
└── frontend/                       # React + Vite single page (questionnaire → results)
    └── src/App.jsx, styles.css
```

## How to run everything

```sh
# Backend (from backend/)
.venv/bin/python -m uvicorn app.main:app --port 8001

# Frontend (from frontend/) — dev server proxies /api to :8001
npm run dev

# Crawler — manual trigger only, no scheduler (from backend/)
.venv/bin/python -m crawler.run
```

The crawler prints a per-program report (HTTP status, tier, reason, new pending changes),
writes tier/timestamps/change-log back into the seed JSON, and stores snapshots + the
append-only change log in `crawler_history.db`. Restart the backend after a crawl — it
loads the seed JSON into memory at startup.

With `ANTHROPIC_API_KEY` exported, the differ automatically switches from hash diffing to
LLM field extraction (`claude-opus-4-8`, structured JSON output): it compares deadline,
funding amounts, and open/closed status against the stored facts, ignoring cosmetic page
changes. Without a key it hash-diffs the page text and flags "content changed, review
manually". **The LLM path has never been exercised live** — no key was available in the
build environment. First thing to do with a key: run the crawler and eyeball its
discrepancy output before trusting it.

## Architecture decisions worth knowing

### Matching (Phase 1, `app/matching.py`)
- **Layer 1 — deterministic eligibility gate.** Hard filter on structured fields
  (revenue minimums, Alberta location, EFP requirement, `min_project_investment`,
  applicant-type keywords for Indigenous/women/young-farmer/CEA programs). A program the
  farmer flatly fails is never shown regardless of semantic similarity.
- **Layer 2 — TF-IDF ranking** of the eligible set: questionnaire free text vs each
  program's `eligible_use`. Tiny hand-rolled TF-IDF (13 docs); deliberately no vector DB.
- **Urgency buckets**, derived from `intake`/`deadline` text: `enrollment_deadline`
  (AgriStability/AgriInvest — use-it-or-lose-it), `rolling`, `invite_only`.

### Crawler + confidence tiers (Phase 2)
- **Tier assignment** (`crawler/run.py::assign_tier`, in priority order):
  1. fetch failed → `flagged`
  2. any `pending_review` change-log entries → `flagged`
  3. unresolved seed-level conflict (`flag` field or `FLAG:` deadline) → `flagged`
     (this is why OFCAF, Emerging Opportunities, Young Farmer, and Women in Ag stay
     flagged until a human resolves them — required by the spec's definition of done)
  4. human-verified within 30 days → `verified` (even if the crawl was inconclusive)
  5. clean crawl confirmation but stale human verification → `crawler_confirmed`
  6. otherwise → `flagged`
- `last_human_verified` (manual confirmation) and `last_crawled` (crawl attempt) are
  deliberately separate fields — do not conflate them. `last_human_verified` was seeded
  from the original `last_verified` (2026-07-06). **Note: that date crosses the 30-day
  window on 2026-08-05, after which crawl runs will legitimately demote clean programs
  from `verified` to `crawler_confirmed` (or `flagged` if the crawl is inconclusive).
  This is intended staleness behavior, not a bug — the fix is a human re-verification
  pass that updates `last_human_verified`.**
- **Change log is append-only.** The crawler only inserts `pending_review` rows (with
  dedupe so the identical pending discrepancy isn't re-appended every run). A human
  review step sets `confirmed`/`rejected` — there is currently **no UI or CLI for this**;
  it was done with direct SQLite `UPDATE` + a matching edit to the seed JSON's
  per-program `change_log` during testing.
- The seed JSON's per-program `change_log` mirrors entries appended by the crawler; the
  SQLite table is the authoritative, queryable record.
- **Snapshots**: one per source (most recent fetch, kept even on failure) in the
  `snapshots` table, for audit.
- All persistence is behind repository interfaces (`ProgramRepository`,
  `CrawlHistoryRepository`) so Postgres can replace JSON/SQLite later without touching
  the matching, API, or crawler logic.

### UI
- Confidence-tier badge (green `verified` / blue `crawler_confirmed` / red `flagged`) is
  **distinct** from the yellow "⚠ Verify before applying" seed-flag badge — they mean
  different things and can appear independently.
- Cards in the enrollment-deadline bucket show a prominent warning banner whenever their
  tier is anything looser than `verified` (wrong data there costs a farmer a full year).
- Card footer shows source URL, `last_human_verified`, and `last_crawled`.

## State as of handover

- First crawler run against all 13 source URLs on 2026-07-09: all HTTP 200.
  Result: 9 `verified`, 4 `flagged` (the seed-conflict programs), 0 `crawler_confirmed`.
- End-to-end change-detection loop verified with a controlled test: tampered OFEP's
  stored snapshot hash → re-crawl flipped it to `flagged` with a `pending_review` entry
  and no facts overwritten → marked the entry `rejected` (simulated human review) →
  re-crawl restored `verified`, with the rejected entry preserved in the log.
- `/api/match` verified returning the new confidence fields; frontend builds clean.
- LLM-mode crawls ran on 2026-07-12 (with an API key) and produced real field-level
  `pending_review` findings — intake pauses for OFEP, OFCAF, RALP, and the Water
  Program, an OFCAF minimum-project-cost change ($2,500 → $10,000), and an
  AgriStability fee-deadline nuance — flipping those programs to `flagged`. **These are
  all awaiting human review**; confirming them means updating the stored facts, marking
  the entries `confirmed`, and bumping `last_human_verified`.
- Per commit `73a01d0`: some source URLs were corrected (producing accepted
  change-log noise), and the women-in-ag-grant fetch fails from this network —
  confirmed not a client bug; it stays honestly `flagged`.

## Known gaps / deliberate non-goals

- **No human-review interface** for the change log (approve/reject) — done via SQLite by
  hand for now. An obvious next feature; remember to update both the DB row and the seed
  JSON entry, and that resolving a conflict should also update `last_human_verified`.
- **No scheduler/cron, no alerting (email/SMS/Slack), no auto-resolution** — all
  explicitly out of scope per the crawler spec.
- **Four source URLs are not program-specific** (agriinvest → afsc.ca root, Indigenous
  funding and Farm Fuel Benefit → alberta.ca root, Young Farmer + Women in Ag → a
  localline.co blog post). Hash diffing "works" on them but is nearly meaningless; the
  LLM differ is written to detect and note "page does not describe this program". Better
  fix: find real program URLs and update the seed (a human-verification action).
- **Change-log dedupe only catches byte-identical `new_value`s.** LLM extraction
  phrases the same finding slightly differently across runs, so near-duplicate
  `pending_review` entries accumulate (visible in the July 12 OFEP/OFCAF/Water Program
  entries). Harmless but noisy; a semantic dedupe or per-field pending cap would fix it.
- No tests beyond the live verification runs described above.
- Phase 1 non-goals still stand: no auth, no persistence of user sessions, no payments,
  no Twilio, no vector DB.

## Environment notes

- Python 3.9.6 (system + venv) — keep code 3.9-compatible (no `match`, no `X | Y` type
  syntax at runtime).
- macOS, backend venv at `backend/.venv`; `httpx` comes in via the `anthropic` package.
- Backend port 8001; Vite dev server on 5173 (CORS already configured for it).
- `crawler_history.db` is gitignored; the seed JSON (including crawler-written fields) is
  tracked and should be committed after each meaningful crawl/review cycle so the fact
  history is versioned.
