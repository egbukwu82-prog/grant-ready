# GrantReady — Phase 1 MVP: One-Shot Build Spec

## What this is
A working local web app that lets an Alberta farmer answer a short questionnaire about
their operation and get back a ranked, accurate list of grant programs they actually
qualify for — with real funding amounts, deadlines, required documents, and a draft
application blurb per program.

This is a **scoped MVP for one build session**, not the full production system described
in the GrantReady product doc. Explicit non-goals are listed at the bottom — do not build
those tonight even if they seem easy to add.

## Ground truth data — do not invent grant details
Use `grantready_seed_programs.json` (attached/provided in the project) as the **only**
source of grant program facts. It contains 13 real Alberta/federal programs with funding
amounts, cost-share rates, eligibility criteria, deadlines, required documents, and source
URLs, compiled from official sources (Alberta.ca, AFSC, RDAR, AAFC) as of July 2026.

Rules:
- Never fabricate a program, dollar figure, deadline, or eligibility rule that isn't in
  the seed file.
- Some entries have a `"flag"` field (e.g. OFCAF's open/closed status conflict, the
  Emerging Opportunities Program mismatch with the original product doc, two
  secondary-source-only entries). Surface these as a visible "verify before applying"
  badge in the UI on that specific program card — don't silently hide the uncertainty
  and don't silently resolve it either.
- Every result shown to the user must display its `source_url` and `last_verified` date.

## Core architecture for tonight
Keep this simple and local — no cloud infra, no external accounts required to run it.

- **Backend:** FastAPI (Python), single service
- **Data layer:** the seed JSON file loaded into memory — no Postgres, no Pinecone/pgvector
  tonight. Structure the code so a real database is a drop-in replacement later (i.e.
  don't hardcode JSON-file assumptions throughout; put data access behind a simple
  repository/interface).
- **Frontend:** React, single page — questionnaire → results view
- **No auth, no accounts, no persistence between sessions** — this is a stateless demo tool
  for tonight.

## Matching logic — two layers, not one
This is the most important design decision in this spec.

**Layer 1 — deterministic eligibility gate (hard filter, no ranking, no semantics):**
Apply the questionnaire answers against each program's structured eligibility fields
(`min_annual_farm_commodities` / `min_gross_farm_income`, `location`, `requires_efp`,
`applicant_type`, `min_project_investment` where present). A program the farmer flatly
doesn't qualify for (e.g. a $30K grain farm against Emerging Opportunities' $2M minimum
investment) must never appear in results, no matter how semantically related the farmer's
answers sound to that program's description.

**Layer 2 — relevance ranking within the eligible set:**
Among programs the farmer actually passes the gate on, rank by fit to what they described
(equipment purchase → OFEP; environmental practices → OFCAF/RALP; income protection →
AgriStability/AgriInvest; value-added processing → On-Farm Value-Added). A lightweight
similarity approach (keyword/TF-IDF match between questionnaire free-text and program
`eligible_use` fields) is sufficient for tonight — full vector RAG is not required to hit
the goal and adds infra dependency for no real gain at this scale (13 programs).

**Urgency tiering — group results into three buckets, not one flat ranked list:**
1. **Enrollment deadline (use-it-or-lose-it):** AgriStability, AgriInvest — missing these
   costs a full year with no late option. Surface with the highest visual urgency.
2. **Rolling/cost-share intake:** OFEP, OFCAF, On-Farm Value-Added, RALP, Water Program,
   Growing Greenhouses, etc. — missing a cycle just means waiting for the next one.
3. **Invite-only / poor fit:** Emerging Opportunities and similar — only show if the
   farmer's profile plausibly clears the minimum investment threshold; otherwise this
   bucket should usually be empty for a typical primary producer.

## Questionnaire (Phase 1 scope, per product doc)
Capture: crop type / livestock type, acreage, annual farm commodity revenue, whether an
EFP exists or not, equipment/technology plans, certifications, whether they're a new/young
farmer, whether they identify as Indigenous or as a woman in ag (for the two targeted
programs) — only ask what's needed to run the eligibility gate and ranking above.

## Output per matched program
- Program name, agency, tier (provincial/federal)
- Funding amount and cost-share rate, in plain language
- Deadline, with urgency tier badge
- Required documents checklist
- One-line "why this matched your answers"
- Source URL + last verified date
- "Verify before submitting" flag if present in the seed data
- A draft application blurb: template-based, filling in the farmer's questionnaire
  answers into a short paragraph they can edit — this does not need an LLM call to work
  tonight; a well-written template per program is enough to demonstrate the feature. If an
  Anthropic API key is available in the environment, a live-generated draft is a nice-to-have
  upgrade, with the template as the fallback.

## Explicit non-goals for tonight — do not build these
- Twilio SMS / WhatsApp delivery
- The automated web crawler / change-detection system
- Real vector database, Pinecone/pgvector, or AWS deployment
- User accounts, login, or saved sessions
- B2B white-label views or commission tracking UI
- Payment processing of any kind

## Definition of done for tonight
A farmer can open the app, answer the questionnaire, and get back a ranked, correctly
grouped, accurately sourced list of the Alberta programs they actually qualify for from the
13 in the seed dataset — with no invented facts, no invisible uncertainty, and a usable
draft blurb per program.
