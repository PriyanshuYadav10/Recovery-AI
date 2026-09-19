# Recovery AI - telephony bridge

Puts the Energy recovery agent on a **real phone call**. Twilio owns the PSTN leg,
this bridge owns the audio, and every decision stays in the FastAPI brain, so the
phone channel behaves exactly like the browser console.

```
Customer phone
   | PSTN
Twilio  --- webhooks --->  bridge (this service, :3100)
                             |  POST /api/bridge/turn
                             v
                     Recovery AI brain (FastAPI :8000)
                     guardrails, escalation, journey, submit
```

## Two pipelines

| `VOICE_PIPELINE` | Needs | Barge-in |
|---|---|---|
| `gather` (default) | Twilio only | Customer can talk over the prompt |
| `stream` | Twilio + Groq | True mid-sentence barge-in |

Start with `gather`: a Twilio account alone is enough to make a real call.

## Audio providers

The stream pipeline needs speech-to-text and text-to-speech. Both default to
**Groq**, because the brain already needs a Groq key - one vendor instead of
three. Either can be swapped independently:

| | `groq` (default) | alternative |
|---|---|---|
| `STT_PROVIDER` | `whisper-large-v3-turbo` | `deepgram` |
| `TTS_PROVIDER` | `canopylabs/orpheus-v1-english` | `elevenlabs` |

Measured on 8kHz phone-quality audio, round trip through mu-law and the
endpointer: **240-460ms** per utterance, transcribed accurately.

> Orpheus is gated behind one-time terms acceptance at console.groq.com. Until
> those are accepted the API answers `400 ... requires terms acceptance`, and the
> bridge says so plainly rather than going silent on the call.

Whisper does not stream, so the bridge does its own endpointing (`SpeechDetector`
in `src/audio.js`): short-term energy with a silence hangover decides when an
utterance has finished, and the same signal triggers barge-in. `VAD_THRESHOLD`
and `VAD_SILENCE_MS` tune it.

`src/audio.js` also carries the codec work - mu-law to PCM and back, WAV
read/write, resampling any TTS output down to the mu-law 8kHz Twilio requires.
It has no dependencies and is unit tested (`npm test`), because codec bugs are
silent and miserable to debug over a phone line.

## Run it

```bash
cd telephony/bridge
npm install
cp .env.example .env     # fill in TWILIO_* and PUBLIC_BASE_URL

ngrok http 3100          # separate terminal - copy the https URL into PUBLIC_BASE_URL
npm start
```

With the brain already running on :8000, place a call:

```bash
curl -X POST http://127.0.0.1:8000/api/calls/dial \
  -H 'Content-Type: application/json' \
  -d '{"lead_id":"EN-1001","voice_mode":"TWILIO"}'
```

A DNC-listed lead is refused before Twilio is ever contacted:

```bash
curl -X POST http://127.0.0.1:8000/api/calls/dial \
  -H 'Content-Type: application/json' -d '{"lead_id":"EN-1004"}'
# {"dialled": false, "blocked_by": "DNC", ...}
```

## Endpoints

| Route | Used by | Purpose |
|---|---|---|
| `POST /dial` | Python adapter | Place the outbound call |
| `POST /transfer` | Python adapter | Warm transfer to `HUMAN_QUEUE_NUMBER` |
| `POST /hangup` | Python adapter | End the leg |
| `POST /twiml/answer` | Twilio | Answer, AMD check, open the conversation |
| `POST /twiml/gather` | Twilio | One turn in the gather pipeline |
| `POST /twiml/status` | Twilio | Call lifecycle + recording URL |
| `WS /media-stream` | Twilio | Audio frames in the stream pipeline |
| `GET /health` | You | Bridge + brain status |

## Guardrails on this leg

- **DNC** gates the dial inside `ConversationManager.start`, before `/dial` is called.
- **Consent** is the first thing said; the disclosure comes from `config/scripts.json`.
- **Answering machines** get a short apology and a hangup - no disclosure, no collection.
- **Recording** is on by default (`TWILIO_RECORD=true`); the URL lands on the status webhook.
- **Warm transfer** dials `HUMAN_QUEUE_NUMBER`. If unset, the ticket still lands in the
  Agent Inbox with full context and the leg ends rather than stranding the customer.

## Trial accounts

A Twilio trial can only dial **verified** numbers, which suits the handout's
"test numbers we provide" constraint. Verify the test number in the Twilio console
before dialling.

## Status

Written against the Twilio Programmable Voice and Deepgram live-transcription APIs.
**Not yet executed against live credentials** - the account keys were not available
in this environment. Syntax-checked (`npm run check`) and wired end to end against the
brain's `/api/bridge/turn` contract, which is covered by the Python test suite.
