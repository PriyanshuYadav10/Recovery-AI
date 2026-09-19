# CIMET integration checklist

What the handout says CIMET will hand over, whether it's arrived, and — for
anything still missing — whether that's actually stopping the demo or not.

| Resource | Status | Blocking? |
|---|---|---|
| Energy field list | Not received — using a self-drafted 8-field set (`config/energy_journey.json`) built from the handout's description | **NON-BLOCKING.** The journey engine reads this file; swapping it for CIMET's real list is a file replacement, not a rewrite. Field IDs and validation rules are the only things that would need to match. |
| Test recording of a real recovery call | Not received for Energy specifically — a real redacted call transcript for a *different* vertical (broadband/internet) was used as behavioural evidence (see below) | **NON-BLOCKING for the demo; would meaningfully improve script realism.** Scripts (`config/scripts.json`) are drafted from the handout's own transcript excerpt, not fabricated. |
| Synthetic lead dataset (ID, last-completed step, test contact) | Not received — self-generated (`data/synthetic_leads.json`, 10 leads spanning fresh/stale, DNC-listed/clear, various sources) | **NON-BLOCKING.** Loader (`JourneyEngine.load_leads`) reads whatever shape is in that file; matching CIMET's exact shape is a data-format check, not new code. |
| Journey-completion sandbox / mock with expected payload shape | Not received — built a local mock (`POST /api/sandbox/journey/submit`) that validates a payload the way a real consumer would (required keys, consent/DNC/disclosure flags, per-field regex/enum/integer rules) and issues a reference | **NON-BLOCKING.** `JourneySubmitClient` already speaks real HTTP; point `JOURNEY_SUBMIT_URL` (`.env`) at CIMET's endpoint and the client switches from the in-process mock to a live POST with no code change. |
| Stable, dedicated on-site internet | N/A until event day | — |
| On-site mentors (platform/agents teams) | N/A until event day | Use them to validate the field list and payload shape as early as possible — that single conversation would retire the two biggest "self-drafted" items above. |
| ViciDial / SIP credentials | Not received | **NON-BLOCKING.** `ViciDialAdapter` is a deliberate clean-boundary stub — it reports `not_configured` rather than faking a connection. The demo's primary voice path is browser mic + (optionally) a real Twilio call via `telephony/bridge`, neither of which needs ViciDial. |
| CIMET sandbox / API credentials generally | Not received | Same as above — every CIMET-shaped integration point in this repo is a named env var or a single config file, specifically so a credential arriving mid-event is a five-minute change, not a rebuild. See [MANUAL_STEPS.md](MANUAL_STEPS.md) §7 for the exact list. |
| Demo environment verified on-site | Not yet possible remotely | Run the checklist in MANUAL_STEPS.md §8 the moment you're on the venue network. |

## On the redacted call transcript that *was* reviewed

A real, redacted outbound sales call transcript (internet/broadband plan,
not Energy) was supplied during this build and reviewed for behavioural
evidence — **not** used as a source of Energy-specific wording, since it's
the wrong vertical and the hackathon scope is Energy only. What it did
change, directly:

- Added guardrail patterns for **soft declines** that never use the word
  "interested" — *"I'll just stay where I am,"* *"I couldn't be bothered,"*
  *"not worth switching."* The transcript's customer declines exactly this
  way twice; the guardrail didn't previously catch either phrasing.
- Confirmed by direct evidence (not assumption) that the real-world pattern
  for the payment guardrail is: **mute the recording before collecting
  payment**, then take card details through a separate web form — which is
  exactly the boundary this build enforces (`NO_PAYMENT` → immediate
  handoff, never collected by voice).

No Energy field names, scripts, or pricing details were taken from it.

## Bottom line

Nothing on this list is currently blocking a live demo. Every item is a
config or data swap away from the real thing, on purpose — that was a
design goal from the start, not a last-minute save.
