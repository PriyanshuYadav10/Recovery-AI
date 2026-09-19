import express from 'express';
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import twilio from 'twilio';
import { config, assertPipelineReady, assertTwilioReady } from './config.js';
import { dial, transfer, hangup } from './dialer.js';
import { openingLine, sendTurn, health as brainHealth } from './brain.js';
import { handleMediaStream } from './agent.js';

assertTwilioReady();
assertPipelineReady();

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: false }));

// recovery-ai call_id <-> Twilio CallSid, both directions.
const byCallId = new Map();
const bySid = new Map();

function link(callId, callSid) {
  if (!callId || !callSid) return;
  byCallId.set(callId, callSid);
  bySid.set(callSid, callId);
}

// ------------------------------------------------ control plane (from Python)

app.post('/dial', async (req, res) => {
  const { to, metadata = {} } = req.body || {};
  try {
    const result = await dial({ to, callId: metadata.call_id, leadId: metadata.lead_id });
    link(metadata.call_id, result.callSid);
    res.json({ ...result, status: 'dialling', mode: 'TWILIO', pipeline: config.pipeline });
  } catch (err) {
    res.status(502).json({ status: 'dial_failed', error: err.message });
  }
});

app.post('/transfer', async (req, res) => {
  const { callId, callSid, target } = req.body || {};
  const sid = callSid || byCallId.get(callId);
  if (!sid) {
    return res.status(404).json({ status: 'no_live_call', callId });
  }
  try {
    res.json(await transfer({ callSid: sid, target }));
  } catch (err) {
    res.status(502).json({ status: 'transfer_failed', error: err.message });
  }
});

app.post('/hangup', async (req, res) => {
  const { callId, callSid } = req.body || {};
  const sid = callSid || byCallId.get(callId);
  if (!sid) return res.json({ status: 'already_ended' });
  try {
    res.json(await hangup(sid));
  } catch (err) {
    res.status(502).json({ status: 'hangup_failed', error: err.message });
  }
});

app.get('/health', async (_req, res) => {
  let brain = { ok: false };
  try {
    brain = await brainHealth();
  } catch (err) {
    brain = { ok: false, error: err.message };
  }
  res.json({
    ok: true,
    service: 'recovery-ai-bridge',
    pipeline: config.pipeline,
    publicBaseUrl: config.publicBaseUrl || null,
    humanQueueConfigured: Boolean(config.humanQueueNumber),
    liveCalls: byCallId.size,
    brain
  });
});

// ------------------------------------------------------- Twilio webhooks

function gatherTwiml(callId, prompt, { hangupAfter = false } = {}) {
  const vr = new twilio.twiml.VoiceResponse();
  if (hangupAfter) {
    if (prompt) vr.say({ language: config.language }, prompt);
    vr.hangup();
    return vr.toString();
  }
  // <Say> nested inside <Gather> lets the customer talk over the prompt,
  // which is the barge-in the gather pipeline can offer.
  const gather = vr.gather({
    input: 'speech',
    action: `${config.publicBaseUrl}/twiml/gather?callId=${encodeURIComponent(callId)}`,
    method: 'POST',
    speechTimeout: 'auto',
    language: config.language,
    actionOnEmptyResult: true
  });
  if (prompt) gather.say({ language: config.language }, prompt);
  return vr.toString();
}

app.post('/twiml/answer', async (req, res) => {
  const callId = req.query.callId;
  const callSid = req.body.CallSid;
  const answeredBy = (req.body.AnsweredBy || 'human').toLowerCase();
  link(callId, callSid);

  // Answering machine: no disclosure, no data collection, no pressure.
  if (answeredBy.includes('machine')) {
    const vr = new twilio.twiml.VoiceResponse();
    vr.say(
      { language: config.language },
      'Sorry we missed you. We will try again another time. Goodbye.'
    );
    vr.hangup();
    return res.type('text/xml').send(vr.toString());
  }

  if (config.pipeline === 'stream') {
    const vr = new twilio.twiml.VoiceResponse();
    const connect = vr.connect();
    connect.stream({
      url: `wss://${req.headers.host}/media-stream?callId=${encodeURIComponent(
        callId
      )}&callSid=${encodeURIComponent(callSid)}`
    });
    return res.type('text/xml').send(vr.toString());
  }

  try {
    const prompt = await openingLine(callId);
    res.type('text/xml').send(gatherTwiml(callId, prompt));
  } catch (err) {
    console.error('[bridge] opening line failed:', err.message);
    const vr = new twilio.twiml.VoiceResponse();
    vr.say({ language: config.language }, 'Sorry, we are unable to continue right now. Goodbye.');
    vr.hangup();
    res.type('text/xml').send(vr.toString());
  }
});

app.post('/twiml/gather', async (req, res) => {
  const callId = req.query.callId;
  const callSid = req.body.CallSid;
  const speech = (req.body.SpeechResult || '').trim();
  const confidence = Number(req.body.Confidence || 0.8);
  link(callId, callSid);

  if (!speech) {
    return res
      .type('text/xml')
      .send(gatherTwiml(callId, "Sorry, I didn't catch that. Could you say it once more?"));
  }

  try {
    const turn = await sendTurn(callId, speech, confidence);

    if (turn.should_transfer) {
      const vr = new twilio.twiml.VoiceResponse();
      vr.say({ language: config.language }, turn.assistant_message);
      if (config.humanQueueNumber) {
        const dialVerb = vr.dial({ answerOnBridge: true });
        dialVerb.number(config.humanQueueNumber);
      } else {
        // No queue number configured - the ticket is already in the Agent
        // Inbox, so end the leg rather than leaving the customer waiting.
        vr.hangup();
      }
      return res.type('text/xml').send(vr.toString());
    }

    res
      .type('text/xml')
      .send(gatherTwiml(callId, turn.assistant_message, { hangupAfter: turn.ended }));
  } catch (err) {
    console.error('[bridge] gather turn failed:', err.message);
    res
      .type('text/xml')
      .send(gatherTwiml(callId, 'Sorry, something went wrong on our side. Goodbye.', { hangupAfter: true }));
  }
});

app.post('/twiml/status', (req, res) => {
  const callId = req.query.callId;
  const { CallSid, CallStatus, RecordingUrl } = req.body;
  console.log(`[bridge] call ${CallSid} -> ${CallStatus}${RecordingUrl ? ` (recording ${RecordingUrl})` : ''}`);
  if (['completed', 'busy', 'no-answer', 'failed', 'canceled'].includes(CallStatus)) {
    const sid = byCallId.get(callId);
    byCallId.delete(callId);
    if (sid) bySid.delete(sid);
  }
  res.sendStatus(200);
});

// --------------------------------------------------------------- streaming

const server = createServer(app);
const wss = new WebSocketServer({ server, path: '/media-stream' });

wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  handleMediaStream(ws, {
    callId: url.searchParams.get('callId'),
    callSid: url.searchParams.get('callSid')
  });
});

server.listen(config.port, () => {
  console.log(`[bridge] Recovery AI telephony bridge on :${config.port}`);
  console.log(`[bridge] pipeline=${config.pipeline} brain=${config.recoveryApiUrl}`);
  if (!config.humanQueueNumber) {
    console.log('[bridge] HUMAN_QUEUE_NUMBER unset - handoffs queue in the Agent Inbox only.');
  }
});
