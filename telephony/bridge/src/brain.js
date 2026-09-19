import { config } from './config.js';

/**
 * The bridge owns audio only. Every decision - what to ask, when to escalate,
 * whether to submit - stays in the FastAPI brain, so the phone channel and the
 * browser console behave identically.
 */

async function call(path, { method = 'POST', body } = {}) {
  const res = await fetch(`${config.recoveryApiUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const err = new Error(`${path} -> HTTP ${res.status}: ${text.slice(0, 200)}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

/** Opening line for a call the brain has already started (disclosure + consent). */
export async function openingLine(callId) {
  const snap = await call(`/api/calls/${callId}`, { method: 'GET' });
  const assistantTurns = (snap.transcript || []).filter((t) => t.role === 'assistant');
  return assistantTurns.length
    ? assistantTurns[assistantTurns.length - 1].text
    : 'Hello, thanks for taking the call.';
}

/** One customer utterance in, one agent reply out. */
export async function sendTurn(callId, text, speechConfidence = 0.9) {
  return call('/api/bridge/turn', {
    body: { call_id: callId, text, speech_confidence: speechConfidence }
  });
}

export async function health() {
  return call('/api/health', { method: 'GET' });
}
