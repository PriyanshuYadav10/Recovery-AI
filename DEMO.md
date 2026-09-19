# Recovery AI - judge demo script (~5:00)

Backend on :8000, Flutter console in Chrome. Bridge + ngrok only if demoing a real call.

## 0:00 - The problem
CIMET recovers dropped Energy journeys with human agents reading scripts and typing answers,
one call at a time. We built an AI that finishes suitable recoveries - and knows when to
hand the phone back.

## 0:30 - Start a recovery
**RUN SUCCESS SCENARIO**. Narrate the order: DNC check -> recording disclosure -> consent ->
resume from what we already know. Point out the agent never asks for the postcode, property
type or ownership - those were captured before the customer dropped out.

## 1:15 - Collection and the journey bar
Only the missing fields are asked. Watch the progress bar tick and the extracted fields
populate. Open **Why did AI do that?** on one ask.

## 1:45 - The journey is actually submitted
The green bar at the bottom: **JOURNEY SUBMITTED - ref CIMET-ENERGY-xxxxxxxx**, HTTP 201.
The agent speaks the reference back to the customer. Show `GET /api/sandbox/submissions` -
a separate consumer validated the payload and issued that reference.

> If asked "is that real?": `JOURNEY_SUBMIT_URL` points at the built-in sandbox. Point it at
> CIMET's and the same client does a real HTTP POST - no code change.

## 2:15 - Messy human
**RUN MESSY CALL**. Interrupt, "I'm actually at work", then the self-correction
"actually I meant house, not apartment" - the field updates rather than the agent arguing.

## 2:45 - Frustration and the handoff (the moment)
**RUN HANDOFF SCENARIO**. Customer: *"I've already told you this twice. Just give me a person."*
Phases: frustration -> human request -> preparing -> context packaged -> human ready.

## 3:15 - The handoff lands somewhere
Click **AGENT INBOX**. The ticket is waiting, carrying the brief, every field collected and
the full transcript. Claim it as Aarav - the first line the human says is
*"I can see what Aisha has already provided, so you won't need to repeat those details."*
Type a reply and resolve it. **This is the difference between showing a brief and doing a handoff.**

## 3:45 - Guardrails
**RUN DNC BLOCK**. The lead is on the register; the call ends before the phone rings.
Then mention the rest: card details escalate rather than being captured, no advice is given,
"not interested" ends the call with no retry loop, and every call writes a recording artifact
because the disclosure promised one.

## 4:00 - Who gets called first
Point at the **CALL QUEUE** on the landing page. The dialler rings leads in order of
recovery propensity, not arrival - a scikit-learn model, 1.78x lift over calling in
arbitrary order, each score carrying its reasons. Say plainly that it is trained on
synthetic history because no real outcome data exists, and that DNC leads are removed
before ranking rather than ranked and skipped.

## 4:15 - Efficiency, measured
Back on the landing page: the **VS. THE MANUAL WORKFLOW** strip. Handle time, fields typed by
an agent (8 -> 0), script lookups (8 -> 0), journeys per agent hour. Say plainly that the
baseline in `config/manual_baseline.json` is a placeholder until the real recording is
measured, and that the note states whether AI handle time was measured or estimated.
Honest numbers beat impressive ones.

## 4:30 - A real phone call
If credentials are in place: `POST /api/calls/dial` and let it ring a verified test number.
If not: show `telephony/bridge/` and say what is true - the Twilio webhooks, media streaming,
barge-in and warm transfer are written, and the full conversation has been driven through
that exact code path by replaying Twilio's webhooks; only the PSTN hop is unproven.

## If a judge asks "how do you know it works?"
`PYTHONPATH=. python evals/run_evals.py` - 106 labelled cases across intent and
extraction, per-class scores, every failure printed. It found eight defects on its
first run, two of them guardrail breaches. CI runs it as a gate at macro-F1 0.90.

## Close
"Teach the phone to listen - and teach it when to hand the phone back."

---

## If something breaks

| Symptom | Fix |
|---|---|
| Landing page shows backend offline | `cd backend && PYTHONPATH=. python run.py` |
| Inbox empty | Run the handoff scenario first |
| Receipt bar missing | Only appears once a journey submits or escalates |
| Bridge health shows `brain.ok: false` | The API is not on :8000 |
