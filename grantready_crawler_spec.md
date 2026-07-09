# GrantReady — Crawler & Confidence-Tier System: Build Spec

## What this is
Phase 1 built a working matching engine on a **manually curated, one-time snapshot** of 13
grant programs. That was correct for a one-night MVP, but it doesn't scale, and it's already
shown its limits — the OFCAF status conflict and the Emerging Opportunities figure mismatch
were both caught by hand, once, at compile time. Nothing currently notices if a program's
deadline, funding cap, or open/closed status changes tomorrow.

This session builds the system that keeps the seed data honest going forward: a crawler that
re-checks each program's official source, detects when something has changed, and assigns a
**confidence tier** to every fact instead of treating all data as equally fresh.

**Read `grantready_seed_programs.json` and `grantready_oneshot_spec.md` from last night's
build before starting** — this system extends that backend, it doesn't replace it.

## The core principle — carried over from Phase 1, non-negotiable
The crawler's job is to **detect and flag, never to silently resolve.** If a fetched page
looks different from what's on file, that's a flagged discrepancy for a human to confirm —
not an automatic overwrite. The exact failure this prevents: a crawler that quietly "corrects"
AgriStability's deadline based on a bad scrape is worse than no crawler at all, because it
removes the visible uncertainty a human would otherwise have caught. Detection is cheap and
should run freely. Overwriting a fact a farmer might rely on requires a confirmation step.

## Architecture
Extend the existing FastAPI backend — don't stand up a separate service.

- **`crawler/sources.py`** — a `Source` abstraction: given a program's `source_url`, fetch
  the page and return raw text content. Build this generically (URL in, text out, plus
  metadata like fetch timestamp and HTTP status) rather than hardcoded to grant pages
  specifically — keep the fetch/diff mechanism reusable, even though tonight's scope is
  grants only.
- **`crawler/differ.py`** — compares newly fetched content against the last stored snapshot
  for that source. A raw text hash is enough to detect "something changed" at minimum. If
  `ANTHROPIC_API_KEY` is set, use it to extract specific fields (deadline, funding amount,
  open/closed status) from the fetched text and diff those against the structured values
  already in the seed data — this catches meaningful changes and ignores cosmetic ones
  (page redesigns, unrelated copy edits). Without a key, fall back to raw-content-hash
  diffing and flag "content changed, review manually" rather than attempting extraction.
- **`crawler/run.py`** — a manual CLI entry point (`python -m crawler.run`) that crawls all
  13 programs' source URLs once and reports results. No scheduler, no cron, no background
  service tonight — see non-goals.
- Store one raw snapshot per source (most recent fetch) for audit purposes, plus a
  **change log** appended to, never overwritten, so a conflict discovered tonight doesn't
  erase the record of what the data looked like before.

## Persistence — this is new, be deliberate about it
Phase 1 kept everything in `grantready_seed_programs.json`, loaded into memory. That's
fine for 13 static records, but the crawler introduces state that actually needs to grow
and be queried over time — don't force that into the same flat file.

- **`grantready_seed_programs.json` stays the source of truth for current facts** per
  program (deadline, funding, eligibility, confidence_tier, last_crawled,
  last_human_verified). It's small, human-readable, and stays git-trackable.
- **Add a local SQLite database (`crawler_history.db`)** for the append-only change log
  and raw fetched snapshots — this is the part that grows with every crawl run and needs
  real querying (e.g. "everything still `pending_review`"). SQLite requires no server, no
  account, and no hosting decision — it does not violate the "no Postgres tonight"
  non-goal, it's just a proper embedded database sized for what this session actually
  needs.
- Put SQLite access behind the same kind of repository interface Phase 1 used for the
  JSON file, so swapping in Postgres later (once this needs to run on a server rather than
  your laptop) is a config change, not a rewrite.

## Confidence-tier data model
Add to each program in the seed data (or its replacement structure):
- `confidence_tier`: one of `verified` (a human confirmed this fact recently),
  `crawler_confirmed` (crawler fetched the source and found no discrepancy),
  `flagged` (crawler detected a possible change, fetch failure, or the source has gone
  stale beyond a reasonable window — define "stale" as no successful crawl in 30+ days)
- `last_crawled`: timestamp of the most recent crawl attempt, regardless of outcome
- `last_human_verified`: timestamp of the most recent manual confirmation (this is
  distinct from `last_crawled` — don't conflate them)
- `change_log`: append-only list of `{timestamp, field, old_value, new_value, status}` —
  status is `pending_review` until a human confirms it, then `confirmed` or `rejected`

## UI updates
Every program card already shows `source_url` and `last_verified`. Extend this to show
`confidence_tier` as a distinct badge from the existing "verify before applying" flag —
they mean different things. A program can be un-flagged but still only `crawler_confirmed`
rather than `verified`. The **enrollment-deadline bucket (AgriStability, AgriInvest)**
should visually distinguish `verified` from anything looser — per the original spec, wrong
data in that bucket costs a farmer a full program year, so it deserves the strictest bar.

## How to run it tonight
This session's deliverable is the crawl mechanism and a way to trigger it manually and see
results — not a live, always-on service. Definition of done includes actually running it
against all 13 real source URLs from last night's seed data and reviewing what it finds.

## Non-goals for this session — do not build these
- No scheduler, cron job, or background service — manual trigger only
- No email/SMS/Slack alerting on detected changes — that's Twilio-scoped, still deferred
- No auto-resolution of conflicts — every detected change is `pending_review`, always
- No expansion to new grant programs beyond the existing 13 — that's a separate task
- No generic "compliance monitoring" product — build the fetch/diff mechanism reusably,
  but do not build features, schemas, or UI for any domain other than GrantReady's grants

## Definition of done
Running `python -m crawler.run` against the 13 real source URLs from last night's seed
data completes without crashing, correctly leaves the OFCAF conflict as `flagged` rather
than resolving it one way or the other, assigns a sensible confidence tier to each of the
13 programs based on real fetch results, and appends to the change log rather than
silently overwriting prior data. The UI shows the new confidence-tier badges without
breaking anything from last night's build.
