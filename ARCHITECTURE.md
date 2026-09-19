# Architecture — Recovery AI

Prototype for CIMET Energy journey recovery. Production-minded prototype
architecture — not a claim of production readiness.

## System diagram

```
                     ┌────────────────────────┐
                     │      VOICE LAYER        │
                     │  Browser mic (default)  │
                     │  Twilio bridge (opt-in) │
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │      SPEECH LAYER        │
                     │  Browser STT / Groq      │
                     │  Whisper (phone path)    │
                     └────────────┬────────────┘
                                  │ text + speech_confidence
                     ┌────────────▼────────────┐
                     │   CONVERSATION MANAGER   │  ← orchestrator, owns state
                     └────────────┬────────────┘
                                  │
        ┌─────────────┬──────────┼──────────┬─────────────┐
        ▼             ▼          ▼          ▼             ▼
  INTENT ENGINE  FIELD EXTRACTOR  CONFIDENCE  ESCALATION  GUARDRAIL
   (rules+LLM)    (rules first,    ENGINE      ENGINE      ENGINE
                   LLM fills gaps)                        (deterministic)
        │             │          │          │             │
        └─────────────┴──────────┼──────────┴─────────────┘
                                  ▼
                     ┌────────────────────────┐
                     │     JOURNEY ENGINE      │  ← state machine + validation
                     └────────────┬────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
        SUBMISSION CLIENT   HANDOFF QUEUE      AUDIT / RECORDER
        (→ sandbox/CIMET)   (→ Agent Inbox)    (→ SQLite + JSON)
                                  │
                     ┌────────────▼────────────┐
                     │   GROQ LLM (optional)    │  ← language only, never
                     │  qwen/gpt-oss ladder     │    a business decision
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │     RESPONSE / TTS       │
                     └────────────────────────┘
```

## The one rule that matters

```
CORRECT                          NEVER
──────────────────────────       ──────────────────────
customer text                    customer text
   │                                │
   ▼                                ▼
LLM (language only)               LLM
   │                                │
   ▼                                ▼
structured hint                  business action
   │                             (skip validation,
   ▼                              skip guardrails,
rules validate + decide           submit unchecked)
   │
   ▼
business action
```

Concretely, in `field_extractor.py`: the deterministic matcher runs first: if
it produces a confident match, that value wins outright, even if the LLM hint
disagrees — the disagreement is recorded (`llm_disagreed_with`) but never
acted on. The LLM hint is only trusted to fill a gap the rules found nothing
for, and even then the value still has to pass the same journey validation
(regex/enum/integer) as everything else. A hallucinated enum value from the
LLM is rejected the same way a mis-heard one from the customer would be.

This was not always true — an earlier version let the LLM hint win outright,
and it silently overrode a correct rule match. See `test_core.py::test_confident_rules_beat_a_wrong_llm_hint`.

The same "detect once, act once" discipline applies to escalation: a signal
the deterministic guardrail already classified (anger, off-script/advice) is
not reclassified and re-scored by the intent engine a second time on the same
utterance — that double-count previously burned through the intended "two
strikes" grace period in a single remark. See
`ConversationManager.handle_utterance` (the `gr_decision` reuse) and
`test_core.py::test_groq_survives_control_characters_in_the_response` /
the scenario suite's `9_frustration` case.

## Components

| Component | File | Responsibility |
|---|---|---|
| ConversationManager | `app/ai/conversation_manager.py` | Orchestrates one call end to end; owns the state machine transitions |
| IntentEngine | `app/ai/intent_engine.py` | Classifies what the customer just did (busy, decline, correction, provide-info, …) |
| FieldExtractor | `app/ai/field_extractor.py` | Rules-first, LLM-assisted extraction of one journey field from an utterance |
| ConfidenceEngine | `app/ai/confidence_engine.py` | Combines speech/intent/field/journey confidence into a single re-ask decision |
| EscalationEngine | `app/ai/escalation_engine.py` | Weighted scoring + critical-signal short-circuit (payment, human request) |
| GuardrailEngine | `app/ai/guardrail_engine.py` | Deterministic pattern rules: consent, payment, decline, advice, human request, anger |
| ScriptEngine | `app/ai/script_engine.py` | Renders `config/scripts.json` lines with field/value interpolation |
| JourneyEngine | `app/journey/engine.py` | Loads `config/energy_journey.json`, tracks missing fields, validates for submit |
| JourneySubmitClient | `app/journey/submitter.py` | Posts the completed payload to the completion sandbox (or CIMET's, via env) and returns a receipt |
| HandoffQueue | `app/services/handoff_queue.py` | Where an escalation actually lands — tickets a human claims in the Agent Inbox |
| MetricsEngine | `app/metrics/engine.py` | Automation rate, handoff wait, vs-manual-baseline comparison |
| AuditLog / CallRecorder | `app/audit/` | Per-call event timeline; JSON call artifact on disk |
| GroqProvider | `app/ai/groq_provider.py` | LLM abstraction with a model fallback ladder and a deterministic no-key mode |
| LeadScorer | `app/ml/scorer.py` | Ranks the dial queue by recovery propensity (scikit-learn, with a heuristic fallback) |
| scenario suite | `app/evaluation/scenarios.py` | 15 named end-to-end business scenarios, PASS/FAIL, deterministic |

## Data flow: a single turn

1. Browser/phone → `POST /api/calls/utterance` with `{call_id, text, speech_confidence}`.
2. `ConversationManager.handle_utterance`:
   a. `GuardrailEngine.evaluate` — deterministic check first (payment, decline, human request, anger, advice, consent-gate).
   b. If not already resolved, `GroqProvider.enrich_turn` — optional language assist, JSON-mode, never required.
   c. `IntentEngine.detect` — combines rules with the (optional) LLM hint.
   d. Depending on the event: collect a field (`FieldExtractor` → `ConfidenceEngine` → maybe `ClarifyING`), confirm, submit, decline, or escalate.
   e. Every state transition and significant decision is written to `AuditLog`.
3. Response carries `assistant_message`, the new `state`, `radar` (live UI panel data), `journey_progress`, and — on submit/escalate — a `receipt` or `handoff_ticket_id`.

## Journey configuration (not hardcoded into any prompt)

```
config/
  energy_journey.json   # 8 fields: id, section, required, label, question,
                         # validation (regex/enum/integer), aliases, examples
  scripts.json           # one line per section/field/objection — the
                         # source of truth the handout asks for
  manual_baseline.json   # documented manual-workflow numbers the AI is
                         # measured against (placeholder until CIMET's
                         # recording is measured)
```

If CIMET supplies the real Energy field list or payload shape during the
event: replace `config/energy_journey.json` and point
`JOURNEY_SUBMIT_URL` (see `.env.example`) at their sandbox. Nothing else
in the codebase names an Energy field directly — the journey engine reads
the config, the extractor validates against whatever `validation` block
each field carries.

## Guardrails (deterministic, not prompted)

| Guardrail | Where |
|---|---|
| DNC gates the dial | `ConversationManager.start`, before `telephony.start_call` — checked before the phone would ring, not after |
| Consent first | Disclosure is the first thing said; no field is asked before consent is granted |
| No card data by voice | `NO_PAYMENT` pattern → immediate `SENSITIVE` escalation, critical (score-independent) |
| No advice | `NO_ADVICE` pattern → scripted decline; escalates only on a second occurrence |
| Respect "no" | `RESPECT_NO` → thank, log, end, no retry loop — including soft declines like "I'll just stay where I am" (see below) |
| Test data only | `data/synthetic_leads.json`, `data/lead_history.json` — no real PII anywhere in the repo |

The soft-decline patterns (`stay where i am`, `couldn't be bothered`, `not
worth switching`, `rather not`, `i'll pass`) were added directly from a real
(unrelated-vertical) redacted call transcript reviewed during this build —
real customers decline without ever saying "not interested," and missing
that would mean the no-pressure guardrail simply doesn't fire for them.

## Escalation signals

ANGER · CONFUSION · OFF_SCRIPT · SENSITIVE · HUMAN_REQUEST · LOW_CONFIDENCE

`SENSITIVE` and `HUMAN_REQUEST` are critical — they escalate on the first
occurrence, independent of score. Everything else accumulates a weighted
score (see `escalation_engine.py::WEIGHTS`) against a threshold, with two
explicit "immediate" shortcuts: three confusion failures on the same field,
or two anger hits. Getting this right required fixing a double-counting bug
where the guardrail layer and the intent-event layer each independently
scored the same utterance — see the "one rule that matters" section above.

## Explainability

Every significant decision produces a `WhyAction` (`action`, `reason`,
`category`) surfaced in the console as "Why did AI do that?" — e.g. *"Escalated
because the customer explicitly requested a human"*. This is a structured,
rule-derived explanation, not exposed chain-of-thought; the LLM's own
reasoning tokens (where a model returns them) are stripped before display.

## Observability

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service, Groq status/model, active sessions, handoff queue depth |
| `GET /api/metrics` | Automation rate, handoffs, submissions, vs-manual comparison |
| `GET /api/audit?limit=` | Cross-call event timeline (live sessions + persisted) |
| `GET /api/evaluation` | The 15 named business scenarios, run live, PASS/FAIL |
| `GET /api/model/status` | Lead-scoring model card: version, algorithm, held-out metrics |
| `GET /api/calls/{id}/replay` | Full transcript + timeline + why-log + payload for one call |

## Telephony integration boundary

`TelephonyAdapter` is the seam: `start_call / end_call / transfer_call /
send_audio / receive_audio`. Four implementations exist —
`BrowserVoiceAdapter` (default demo path), `MockTelephonyAdapter`
(scripted/simulated), `TwilioBridgeAdapter` (real PSTN via
`telephony/bridge`), and `ViciDialAdapter` (clean stub — CIMET's own
dialler is not faked; the adapter exists so wiring it in later is a
config change, not a rewrite). The console shows which mode is active.

## Future production path (not built, explicitly out of scope here)

- Replace in-process `sessions: dict` with a durable session store (already
  SQLite-backed for calls/handoffs/submissions; would need a proper queue for
  concurrency beyond a single demo laptop).
- Replace the synthetic lead-scoring dataset with real CIMET outcome data.
- Real monitoring/alerting (this prototype has structured logs and a
  metrics endpoint, not a monitoring stack).
- CI running against real infrastructure rather than the built-in mocks.
