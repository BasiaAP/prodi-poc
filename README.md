# Prodi — reusable multi-agent Product BOT (PoC)

A **functional** proof of concept of the Prodi Product BOT from the
[Prodi PoC page](https://etherapists.atlassian.net/wiki/spaces/PT/pages/5906956292/Product+BOT-+Prodi+PoC).

The design goal is reuse: **one consistent request-validation engine + a set of
agents that plug into any communicator** (Slack, Teams, …). Connecting Prodi to
another team's bot is *one adapter + one config file* — no changes to the core.

```
communicator  ──►  Adapter  ──►  Prodi core (orchestrator)  ──►  agents
  (Slack /         (normalise      • MUST HAVES gating           • validation engine
   Teams /          events)        • QA → Tech → Product Opt      • business case
   CLI)                            • routing + feedback           • reporting …
```

## Why it's reusable

* **`prodi.handle(IncomingMessage) -> [Reply]`** is the entire integration
  surface. Adapters only translate platform events to/from these two dataclasses.
* **The validation engine is deterministic and config-driven** — identical
  behaviour on every platform. Other teams customise `config/prodi.yaml`
  (must-haves, keywords, owners, boards, model tiers), not the code.
* **Model routing in one place**: each agent declares a tier (opus/sonnet/haiku);
  concrete model ids live in config, so the cost split is tuned centrally.
* **LLM-optional**: ships with a deterministic stub backend so it runs anywhere
  with no API keys; set `PRODI_LLM=anthropic` to use real models.

## Run it (no keys needed)

```bash
pip install -r requirements.txt
python -m pytest -q                # 10 tests, all green
python demo/demo_session.py        # scripted end-to-end: product / bug / dup / report
python -m prodi.adapters.cli       # interactive: type '#req <your request>'
```

## The agent set (from the PoC agent table)

| Agent | Tier | Temp | Role |
|---|---|---|---|
| Intake & Triage (orchestrator) | sonnet | 0.15 | Single entry point; MUST HAVES gate; routing |
| Product Optimization | opus | 0.3 | Validate vs roadmap, dedup, strategy, owner/board |
| Business Case engine | opus | 0.5 | Standardized overview, B2B2C + channel mapping |
| QA (Oscar-based) | sonnet | 0.1 | Completeness + thin-content checks |
| Tech / Categorization | haiku | 0.1 | Bug/incident vs product; category tagging |
| Reporting | sonnet | 0.2 | Owner-attributed weekly/all-hands draft |
| Info Seeker | sonnet | 0.1 | Link release notes; seek "Available by" date |
| Update | haiku | 0.1 | Post release-notes update once date is set |

## What the engine enforces (per the PoC)

* **MUST HAVES gating** — product must-haves always; tech must-haves added when
  the request looks like a bug/incident. Collected as a **single form**, not
  one question per message (a native Slack modal when live; a one-message
  fill-in-the-blank reply otherwise) - any field the form reply misses falls
  back to asking just that field. Nothing is processed until the gate is
  satisfied.
* **Bug/incident vs product** classification → incident/bug board.
* **Duplicate check** against the shared idea board (in dev vs planned vs new).
* **Owner assignment by keyword** (White Label→Julia, HealthOS→Rafia,
  CMS→Berke, AI/Zoya→Sofia, Core/mobile→Basia, else blank→escalate).
* **Category / bucket / opportunity-area** recommendation for the PM.
* **Strategy check** (Standardize / Grow / Integrate) and a **confidence
  threshold** that escalates to a named owner when low.
* **Instant feedback**: accepted / needs-more / bug-incident / duplicate.
* **Unified storage** for requests and business cases.

## Add a new communicator (the whole job)

```python
from prodi.adapters.base import PlatformAdapter

class MyChatAdapter(PlatformAdapter):
    def to_incoming(self, event):   # -> IncomingMessage
        ...
    def send(self, reply):          # render reply.text back to your platform
        ...
    def run(self):                  # start your event loop, call self.dispatch(event)
        ...
```

Slack (`prodi/adapters/slack.py`) and Teams (`prodi/adapters/teams.py`) are
included as guarded reference adapters — install the optional dep, set tokens,
and run.

## Layout

```
config/prodi.yaml          # the one file other teams edit
prodi/
  models.py                # IncomingMessage / Reply / Classification / RequestState
  engine.py                # the reusable validation engine
  orchestrator.py          # Prodi: intake gate + routing (prodi.handle)
  llm.py                   # stub + anthropic backends, tiered by agent
  store.py                 # unified storage (JSON-backed)
  jira_store.py            # live Store: creates real Jira tickets
  confluence_store.py      # live Store: publishes real Confluence one-pagers
  jira_idea_board.py       # live duplicate check against the real shared idea board
  agents/                  # the 8 specialist agents (declarative + logic)
  adapters/                # base + cli (working) + slack + teams
demo/demo_session.py       # scripted proof
tests/                     # engine + orchestrator tests
```

## Config knobs (`config/prodi.yaml`)

`bot` (trigger tokens, confidence threshold) · `models` (tier→model id) ·
`must_haves` (product/tech) · `classification` (bug/incident keywords) ·
`owners` (keyword→PM) · `categories` / `opportunity_areas` / `buckets` ·
`routing` (board names) · `idea_board_seed` (offline dedup source; swap for
`jira_idea_board.JiraIdeaBoardChecker` to validate against the real shared
idea board instead — same keyword-overlap matching, injected via
`Prodi(..., idea_board=...)`).

## Not in scope (matches the PoC)

Engineering build/delivery work — Prodi only categorizes, routes and reports.
Live Jira/Confluence/Slack writes are stubbed behind `store.py` and the
adapters for the PoC; swap those implementations to go live.
