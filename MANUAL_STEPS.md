# Manual steps — what you must do yourself

Everything else is automated. This file is the complete list of what isn't,
and exactly where.

## Before the event

### 1. Add your Groq API key

| | |
|---|---|
| **File** | `.env` (project root — copy from `.env.example` if it doesn't exist) |
| **Line** | `GROQ_API_KEY=your_groq_api_key_here` |
| **Value** | Your key from [console.groq.com/keys](https://console.groq.com/keys) |
| **Why** | Without it, every conversation still runs — deterministic/scripted mode, no LLM assist. With it, the intent engine and handoff briefs get language help. **The demo does not require this to work.** |

Also check `GROQ_MODEL` on the same file: it defaults to `qwen/qwen3.8-27b`
(fastest on the model comparison done during this build — see README §
"Reasoning model"). If your key can't reach that model, the app will still
work — `GroqProvider` walks a fallback ladder (`GROQ_FALLBACK_MODELS` in
`backend/app/core/config.py`) and retires dead ids automatically.

### 2. Install dependencies

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd ../frontend && flutter pub get
```

Only needed once, or after a `requirements.txt` / `pubspec.yaml` change.

### 3. Train the lead-scoring model (optional — a trained artifact should already be committed)

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. python app/ml/dataset.py   # regenerate synthetic history
PYTHONPATH=. python app/ml/train.py     # writes app/ml/artifacts/lead_scorer.joblib
```

If skipped, `/api/leads/prioritised` falls back to a documented heuristic —
the call queue still ranks sensibly, just without the trained model.

## On the day

### 4. Start the backend

```bash
cd backend && source .venv/bin/activate && PYTHONPATH=. python run.py
```

Confirm: `curl http://127.0.0.1:8000/api/health` → `"ok": true`.

### 5. Start the Flutter console

```bash
cd frontend && flutter run -d chrome
```

### 6. Allow microphone permission

The first time the browser asks — required only if you demo the live
browser-voice path rather than the scripted demo scenarios (which need no
mic at all).

### 7. If CIMET hands you real integration resources during the event

| Resource | Where it plugs in | How |
|---|---|---|
| Real Energy field list / payload shape | `config/energy_journey.json` | Replace the file; the journey engine reads it directly, nothing else hardcodes a field name |
| Journey-completion sandbox URL | `.env` → `JOURNEY_SUBMIT_URL` | Uncomment and set to their endpoint; `JourneySubmitClient` switches from the in-process mock to a real HTTP POST automatically |
| Sandbox auth token | `.env` → `JOURNEY_SUBMIT_TOKEN` | Same file, sent as `Authorization: Bearer <token>` |
| Synthetic lead dataset | `data/synthetic_leads.json` | Replace with theirs, keeping the same shape (`lead_id`, `known_fields`, `dropped_at`, `dnc_listed`, …) — or tell me the shape and I'll adapt the loader |
| ViciDial / SIP credentials | `backend/app/telephony/adapters.py` → `ViciDialAdapter` | Currently a clean stub (`configured = bool(host and api_user)`); fill in the two methods that raise `NotImplementedError` |
| Twilio number for a real phone call | `telephony/bridge/.env` | `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER`, plus `PUBLIC_BASE_URL` from `ngrok http 3100` |
| Human-agent transfer number | Both `.env` files → `HUMAN_QUEUE_NUMBER` | Used for a real warm transfer on a live call; without it, the handoff still queues correctly in the Agent Inbox |

### 8. Final live test before presenting

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. pytest -q                        # unit + integration
PYTHONPATH=. python tests/demo_script.py      # 4 scripted scenarios end to end
PYTHONPATH=. python evals/run_evals.py        # intent/extraction quality gate
PYTHONPATH=. python evals/run_scenarios.py    # 15 named business scenarios

cd ../frontend && flutter test && flutter build web
```

All of the above should be green. If `/api/evaluation` (the live HTTP
version of the scenario suite) shows anything less than 15/15, do not present
until it's fixed — it was made deterministic specifically so a red result
means a real regression, not a flaky LLM call.

### 9. Present to judges

Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

---

## What you never need to do

- Write or edit prompts to change what fields are collected — that's
  `config/energy_journey.json` and `config/scripts.json`.
- Touch escalation thresholds for the demo — they're tuned and tested
  (`backend/app/ai/escalation_engine.py::WEIGHTS`).
- Worry about secrets in git — `.env` is gitignored; only `.env.example`
  (placeholders only) is committed. Double-check with `git status` before
  any commit if you're unsure.
