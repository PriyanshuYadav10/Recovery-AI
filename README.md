# Recovery AI

Recover dropped Energy comparison journeys with a voice-first AI agent that knows when to step aside.

**Tagline:** Recover the journey. Know when to step aside.

## Problem

CIMET / econnex customers abandon the Energy comparison mid-journey. Today a human agent
rings them back, reads a script, and types the answers into the journey iframe, one call at
a time. This prototype shows an AI voice agent completing suitable recoveries end to end -
and performing a **warm handoff with full context** when it should not continue alone.

## What it does

1. DNC gate **before** the dial - a listed lead never causes the phone to ring
2. Recording disclosure, then consent, before anything is collected
3. Resumes from the lead's last completed step - no repeated questions
4. Collects only the missing Energy fields in natural conversation
5. Deterministic guardrails: consent, no card data, no advice, respect "no"
6. Escalation engine raises a **ticket a human actually claims**, carrying the brief,
   every field and the full transcript
7. Submits the journey payload to the completion sandbox and **speaks back the reference**
8. Measures itself against the documented manual baseline

## Architecture

```
Phone (Twilio)                    Browser (mic + Web Speech)
      |                                    |
      v                                    v
telephony bridge (Node :3100) ------> Recovery AI brain (FastAPI :8000)
  Twilio ASR/TTS or                    |
  Deepgram + ElevenLabs                +-- Intent engine
                                       +-- Field extractor
                                       +-- Emotion / escalation
                                       +-- Guardrail engine (rules, not LLM)
                                       +-- Journey state machine
                                       +-- Submission client --> completion sandbox
                                       +-- Handoff queue ------> Agent Inbox (Flutter)
                                       +-- Recorder / SQLite store
```

Safety-critical decisions are **not** LLM-owned:

| Concern | Owner |
|---|---|
| Consent, DNC, decline, payment, human request | Guardrail engine (rules) |
| Escalation score and critical signals | Escalation engine |
| Journey progression, validation, submission | Journey state machine |
| Conversational phrasing, extraction assist | Groq (optional) |

## Voice paths

| Mode | What it is | Status |
|---|---|---|
| `TWILIO` | Real outbound phone call via the Node bridge | Audio path proven end to end; **the PSTN hop itself not yet run against live credentials** |
| `BROWSER` | Mic + Web Speech + SpeechSynthesis | Working demo path |
| `SIMULATED` | Scripted utterances, no audio | Working, used by the test suite |
| `VICIDIAL` | Adapter stub for CIMET's dialler | Stub |

The phone path has been exercised end to end by posting the exact webhooks Twilio posts -
a full Energy journey completes and a handoff escalates over that code path. Only the PSTN
leg itself is unproven, because no live Twilio credentials were available here.

The stream pipeline runs speech-to-text and text-to-speech on **Groq**, the same
vendor as the reasoning model, so the phone leg needs no extra accounts beyond
Twilio. Whisper transcribes a phone-quality utterance in 240-460ms; the bridge
does its own endpointing and barge-in because Whisper does not stream.

See [telephony/bridge/README.md](telephony/bridge/README.md).

## Journey completion

The payload is **submitted**, not just constructed. `JourneySubmitClient` posts it and keeps
a receipt; the agent reads the reference number back to the customer.

```
POST /api/sandbox/journey/submit   <- built-in mock, validates like a real consumer
GET  /api/sandbox/submissions      <- what the sandbox received
GET  /api/submissions              <- every submission + receipt, survives restart
```

Point `JOURNEY_SUBMIT_URL` at CIMET's sandbox in `.env` and nothing else changes - the client
switches from in-process to a real HTTP POST automatically.

A refused payload is never announced as done: the call escalates to a human instead.

## Warm handoff

Escalation raises a ticket in the queue, carrying the brief, every field collected and the
whole transcript. A human opens the **Agent Inbox**, claims it, and continues the
conversation - the customer never repeats themselves. On a real call the leg is transferred
to `HUMAN_QUEUE_NUMBER` at the same moment; with no number configured the ticket still lands
in the inbox and the system says so rather than stranding the caller.

```
GET  /api/handoffs                      POST /api/handoffs/{id}/claim
GET  /api/handoffs/{id}                 POST /api/handoffs/{id}/message
POST /api/handoffs/{id}/resolve
```

Signals: ANGER, CONFUSION, OFF_SCRIPT, SENSITIVE, HUMAN_REQUEST, LOW_CONFIDENCE.
SENSITIVE and HUMAN_REQUEST escalate immediately; three confusions on one field or two
anger hits also force it; otherwise a weighted score crosses the threshold.

## Efficiency, measured not asserted

`config/manual_baseline.json` holds what the manual workflow costs today. `/api/metrics`
returns a `vs_manual` block comparing the AI run against it - handle time, fields typed,
script lookups, journeys per agent hour.

> The baseline numbers in that file are **placeholders** until the CIMET call recording is
> measured. Replace them there; every figure in the UI follows.

AI handle time is measured wall-clock on a real call, or estimated from transcript length
(165 wpm + 1.2s per turn) on a simulated run. The comparison always states which basis it
used - a simulated run finishing in milliseconds must not masquerade as a time saving.

## Lead prioritisation (which leads to ring first)

The cron picks up dropped leads with no notion of which are worth calling. A
scikit-learn model scores recovery propensity and ranks the queue.

```
GET /api/leads/prioritised   ranked call queue, with reasons per lead
GET /api/model/status        model card: version, algorithm, metrics, provenance
POST /api/model/reload       pick up a retrained artifact without a restart
```

| Piece | Where |
|---|---|
| Feature contract (shared by training and serving) | `backend/app/ml/features.py` |
| Synthetic training data + documented generating process | `backend/app/ml/dataset.py` |
| Training, model selection, evaluation | `backend/app/ml/train.py` |
| Serving, explanations, heuristic fallback | `backend/app/ml/scorer.py` |

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. python app/ml/dataset.py   # regenerate history (seeded)
PYTHONPATH=. python app/ml/train.py     # train + evaluate + write artifact
```

Logistic regression and gradient boosting are cross-validated and the better one
is selected. Held-out results on the current artifact:

| Metric | Value |
|---|---|
| ROC-AUC | 0.723 |
| PR-AUC | 0.529 |
| Brier | 0.185 |
| Precision in the top 20% of the queue | 0.545 vs 0.307 base rate |
| **Lift** | **1.78x** |

> **These numbers describe synthetic data.** There is no real CIMET outcome data
> and the handout forbids real PII, so `dataset.py` generates history from an
> explicit seeded process documented in its docstring. The evaluation shows the
> pipeline recovers a signal that was deliberately planted - it is not evidence of
> real-world accuracy. Retrain on genuine outcomes before trusting any figure here.

Two things the queue gets right regardless of the model: **DNC-listed leads are
removed before ranking**, never ranked and skipped; and if the artifact is missing
the scorer falls back to a documented heuristic that preserves the same ordering,
so the API never breaks because a model was not trained.

## Offline evaluation

The intent engine and the field extractor decide what the agent hears, so they are
measured rather than eyeballed.

```bash
cd backend && PYTHONPATH=. python evals/run_evals.py
PYTHONPATH=. python evals/run_evals.py --fail-under 0.90   # CI gate
```

106 hand-labelled cases (55 intent, 51 extraction) covering compounds,
self-corrections, negations, objections and deliberate misses. The harness prints
every failure and writes `evals/latest_report.json`.

It earned its keep immediately: the first run found eight defects, two of them
guardrail breaches - *"I'll give you my bank details"* was not tripping the payment
boundary, and *"take me off your list"* was not registering as a decline.

> The suite currently passes at 100%, but the cases were written here and the
> engines were then fixed against them. Treat it as a **regression gate**, not an
> unbiased accuracy estimate. It should grow from real call recordings.

## Reasoning model

Groq retires model ids without notice, so the provider walks a ladder rather than
giving up on the first 404. It retires dead ids for the life of the process and
pins whichever model answers.

Check what a key can actually reach:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

Measured round-trip on this account, JSON mode, median of three:

| Model | Latency | Note |
|---|---|---|
| `qwen/qwen3.8-27b` | ~145ms | default - on a phone call latency is the product |
| `openai/gpt-oss-20b` | ~590ms | first fallback |
| `openai/gpt-oss-120b` | ~807ms | second fallback, higher quality |
| `groq/compound-mini` | ~1437ms | too slow for voice |
| `llama-3.3-70b-versatile` | 404 | decommissioned by Groq |

Responses are parsed leniently: reasoning models return a `reasoning` field
containing raw control characters, which a strict JSON parser rejects - that
would otherwise discard a perfectly good reply and drop the call to rules mode.

## Guardrails

| Guardrail | Where it sits |
|---|---|
| DNC gates the dial | `ConversationManager.start`, before `telephony.start_call` |
| Consent first | Disclosure is the first thing said, before any collection |
| No card data by voice | `NO_PAYMENT` rule -> immediate escalation |
| No advice | `NO_ADVICE` rule -> hands to a specialist |
| Respect "no" | `RESPECT_NO` -> thank, log, end. No retry loop |
| Recording | Every call writes `data/recordings/<call_id>.json` |
| Answering machines | Short apology and hangup - no disclosure, no collection |

## Design system

The console is set in CIMET's own visual language, sampled directly from
`docs/CIMET-Hackathon-Handout-v3.pdf` rather than approximated:

| Role | Token |
|---|---|
| Page | `#101124` |
| Panel / callout | `#181A3D`, `#22244A` |
| Accent (the only one) | `#FF5B3D` |
| Text | `#DCDCF2`, `#C3C5E0` |
| Muted labels | `#A9ABCB`, `#8385AB`, `#6A6C92` |
| Faded numerals | `#5C5E82` |
| Rules | `#2B2D55`, `#35376A` |

The system is deliberately two-tone. There is no second bright accent, so status
is carried by intensity instead of hue - orange demands attention, light text is
neutral, faint recedes. `lib/theme/handout.dart` holds the component vocabulary:
numbered section labels (`0 1 · T H E D O M A I N`), the orange-ruled callout,
stat blocks, outline chips, PRIMARY / GOOD TO HAVE badges, faded numeral cards,
the running footer and the cover waveform. Screens compose those rather than
hand-rolling decoration.

Call transcripts are typeset the way the handout sets them: inline mono speaker
tags, a `● REC` marker, and the escalation line rendered as
`↳ FRUSTRATION DETECTED - WARM HANDOFF` in the accent.

## Energy journey

`config/energy_journey.json` - 8 required fields with regex/enum/integer validation and
alias maps. `config/scripts.json` - one line per field plus every objection path.

Fields: postcode, property_type, ownership, current_supplier, fuel_type, has_solar,
household_size, usage_band.

## Containers and CI

```bash
docker compose up brain                      # API on :8000
docker compose --profile telephony up        # add the phone bridge
```

The backend image trains the model at build time if no artifact is committed, so it
is never served on the fallback by accident.

`.github/workflows/ci.yml` runs four jobs: backend tests and demo scenarios, model
training, the eval gate at macro-F1 0.90, bridge syntax, Flutter test and web build,
and both Docker builds. Model metrics and the eval report upload as build artifacts.

## Setup

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend && flutter pub get

# Telephony bridge (optional - only for real phone calls)
cd ../telephony/bridge && npm install && cp .env.example .env
```

`.env` in the project root:

```
GROQ_API_KEY=your_key            # optional - without it, deterministic mode
GROQ_MODEL=llama-3.3-70b-versatile
JOURNEY_SUBMIT_URL=              # optional - defaults to the built-in sandbox
HUMAN_QUEUE_NUMBER=              # optional - phone number for warm transfers
```

## Running

```bash
# API
cd backend && source .venv/bin/activate && PYTHONPATH=. python run.py

# Console
cd frontend && flutter run -d chrome

# Bridge, for a real call (separate terminals)
ngrok http 3100
cd telephony/bridge && npm start
curl -X POST http://127.0.0.1:8000/api/calls/dial \
  -H 'Content-Type: application/json' -d '{"lead_id":"EN-1001","voice_mode":"TWILIO"}'
```

## Demo scenarios

| Scenario | Shows |
|---|---|
| `success` | Full recovery, payload submitted, reference spoken back |
| `messy` | Interruption, "I'm at work", self-correction, still completes |
| `handoff` | Frustration + human request -> brief -> ticket in the Agent Inbox |
| `dnc` | Listed lead blocked before the dial |

## Testing

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. pytest -q                        # 61 tests
PYTHONPATH=. python tests/demo_script.py      # 4 scenarios end to end
PYTHONPATH=. python evals/run_evals.py        # intent + extraction quality

cd frontend && flutter test && flutter build web
cd telephony/bridge && npm test && npm run check
```

## Known limitations

- The Twilio leg has not been placed against live credentials; everything either side of
  the PSTN hop is exercised.
- `config/manual_baseline.json` is placeholder data until the CIMET recording is measured.
- CIMET's real payload shape is not supplied yet; the current shape is documented in
  `config/energy_journey.json` and swappable via `JOURNEY_SUBMIT_URL`.
- Scripts are drafted from the handout, not yet tuned against the real call recording.
- Browser STT quality varies by browser and permissions.
- The lead scoring model is trained on synthetic history; its metrics measure
  pipeline correctness, not real-world accuracy.
- The eval suite is a regression gate written alongside the fixes, not a held-out
  benchmark.
- CI has not been executed - there is no remote for this repo yet.
