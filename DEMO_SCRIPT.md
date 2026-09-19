# Demo script — Recovery AI (~4:40)

Judge-facing timed script. Slides support this; they don't replace it — the
demo is a live run. For the fuller operational runbook (troubleshooting, a
DNC-block beat, the call-queue beat), see [DEMO.md](DEMO.md).

Before starting: backend on `:8000` (`cd backend && PYTHONPATH=. python
run.py`), Flutter console open in Chrome, mic permission already granted.

---

**0:00 — Problem**
"CIMET recovers dropped Energy journeys with human agents reading scripts and
typing answers, one call at a time. We built an AI that finishes suitable
recoveries — and knows exactly when to hand the phone back."

**0:20 — A dropped lead appears**
Open the landing page. Point at the **CALL QUEUE**: dropped leads ranked by a
recovery-propensity model, not called in arbitrary order. Note DNC-listed
leads are removed before ranking, not ranked and skipped.

**0:40 — AI starts the recovery**
Click **START LIVE RECOVERY** (or **RUN SUCCESS SCENARIO** for a guaranteed
run). Narrate the fixed order: DNC check → recording disclosure → consent →
resume from the lead's last completed step. The AI never re-asks a field it
already has.

**1:10 — Natural conversation**
Watch the agent ask only the missing Energy fields. Point at the journey
progress bar ticking and the extracted-fields panel populating live.

**1:40 — Messy interruption**
Run (or narrate) **MESSY CALL**: interrupt, "I'm at work," a self-correction
("actually I meant house, not apartment"). The field updates rather than the
agent arguing or losing its place.

**2:00 — AI confidence / field extraction**
Open **AI Call Radar**: mood, confidence, escalation risk. Open **Why did AI
do that?** on one field ask — a concrete, rule-derived reason, not exposed
chain-of-thought.

**2:20 — Customer frustration**
Run **RUN HANDOFF SCENARIO**. Customer: *"I've already told you this twice,
this is ridiculous"* — then, a second frustrated turn — matching the
handout's own two-turn pacing before a handoff triggers, not a hair-trigger
on the first sharp remark.

**2:30 — Human request / handoff sequence**
UI phases: FRUSTRATION DETECTED → HUMAN REQUEST → PREPARING → CONTEXT
PACKAGED → HUMAN READY.

**2:35 — Warm handoff**
Click **AGENT INBOX**. The ticket is waiting with the brief, every field
collected, and the full transcript. Claim it — the human's first line is
generated context, not a blank "how can I help": *"I can see what you've
already provided, so you won't need to repeat those details."*

**3:00 — Context brief**
Read the brief aloud: reason, customer mood, fields collected, recommended
opening, next action. **The customer never repeats themselves.**

**3:20 — Complete journey / payload**
Back to a completed run (or the success run from earlier): the green
**JOURNEY SUBMITTED** bar — reference number, HTTP status, latency. This is
an actual POST to the completion sandbox and a receipt, not a UI checkmark.

**3:40 — Metrics**
Landing page **VS. THE MANUAL WORKFLOW** strip: handle time, fields typed by
an agent (8 → 0), script lookups, journeys per agent hour. State plainly that
the baseline numbers are placeholders pending CIMET's real call recording —
the honesty of that caveat is part of the pitch.

**4:00 — AI evaluation**
`GET /api/evaluation` (or `python evals/run_scenarios.py`) — 15 named
business scenarios (correct answer, ambiguous answer, interruption,
busy, decline, human request, frustration, repeated confusion, payment,
off-script advice, low confidence, consent denied, full completion), each
driven through a full call, each PASS/FAIL, run live in front of the judges.
This is what "the AI works" means here — a checkable claim per scenario, not
an assertion.

**4:20 — Architecture in one breath**
"The LLM only ever produces a structured hint. Rules validate it, guardrails
gate it, and a confident rule match beats a disagreeing LLM hint outright —
the model assists the conversation, it never owns a decision that matters."

**4:40 — Close**
"Recovery AI doesn't try to replace the human. It automates the predictable
journey, and it knows exactly when the human is needed."

---

## If something breaks live

| Symptom | Fix |
|---|---|
| Landing page shows backend offline | `cd backend && PYTHONPATH=. python run.py` |
| Groq shows "deterministic" mode | Expected without a working `GROQ_API_KEY` — the whole demo still runs, scripted rather than LLM-assisted |
| Agent Inbox empty | Run the handoff scenario first |
| `/api/evaluation` shows fewer than 15/15 | Rerun once — if still failing, check `evals/latest_scenario_report.json` for which case and why; this is a real regression, not flakiness (it was made deterministic specifically so it never flakes) |
