import { config } from './config.js';
import { sendTurn, openingLine } from './brain.js';
import { transfer } from './dialer.js';
import { createStt } from './stt.js';
import { createTts } from './tts.js';
import { muLawToPcm16, SpeechDetector } from './audio.js';

/**
 * Media-stream pipeline (VOICE_PIPELINE=stream).
 *
 * Twilio streams mu-law/8000 in, the bridge decides where each utterance ends,
 * transcribes it, asks the FastAPI brain what to say, and speaks the reply back
 * down the same socket. Every decision - what to ask, when to escalate, whether
 * to submit - stays in the brain, so the phone channel behaves exactly like the
 * browser console.
 *
 * Barge-in: the detector fires as soon as the caller's energy crosses the
 * threshold. Queued audio is dropped in Twilio with a `clear` frame and the
 * in-flight reply is marked stale so it stops mid-sentence, the way a person
 * would when talked over.
 */
export function handleMediaStream(ws, context = {}) {
  const callId = context.callId;
  const stt = createStt();
  const tts = createTts();
  const detector = new SpeechDetector({
    threshold: Number(process.env.VAD_THRESHOLD || 900),
    silenceMs: Number(process.env.VAD_SILENCE_MS || 700)
  });

  let streamSid = null;
  let speaking = false;
  let speechEpoch = 0;
  let transcribing = false;
  let closed = false;

  console.log(`[bridge] stream up - stt=${stt.name} tts=${tts.name}`);

  function clearPlayback() {
    if (streamSid && ws.readyState === 1) {
      ws.send(JSON.stringify({ event: 'clear', streamSid }));
    }
  }

  async function speak(text) {
    if (!text || closed) return;
    const epoch = ++speechEpoch;
    speaking = true;
    try {
      const mulaw = await tts.synthesize(text);
      // The caller started talking while we were synthesising - drop it.
      if (epoch !== speechEpoch || closed) return;

      // Twilio takes 20ms frames: 160 bytes at 8kHz mu-law.
      for (let offset = 0; offset < mulaw.length; offset += 160) {
        if (epoch !== speechEpoch || closed) break;
        const frame = mulaw.subarray(offset, offset + 160);
        if (ws.readyState === 1 && streamSid) {
          ws.send(
            JSON.stringify({
              event: 'media',
              streamSid,
              media: { payload: frame.toString('base64') }
            })
          );
        }
      }
    } catch (err) {
      console.error('[bridge] TTS failed:', err.message);
    } finally {
      if (epoch === speechEpoch) speaking = false;
    }
  }

  async function onUtterance(samples) {
    if (closed || transcribing) return;
    transcribing = true;
    try {
      const text = await stt.transcribe(samples);
      if (!text || text.length < 2) return;
      console.log(`[bridge] heard: ${text}`);

      const turn = await sendTurn(callId, text);
      await speak(turn.assistant_message);

      if (turn.should_transfer && context.callSid) {
        const result = await transfer({ callSid: context.callSid });
        console.log('[bridge] warm transfer:', result.status);
        return;
      }
      if (turn.ended) setTimeout(() => ws.close(), 4000);
    } catch (err) {
      console.error('[bridge] turn failed:', err.message);
    } finally {
      transcribing = false;
    }
  }

  ws.on('message', async (raw) => {
    try {
      const msg = JSON.parse(raw.toString());

      if (msg.event === 'start') {
        streamSid = msg.start.streamSid;
        await speak(await openingLine(callId));
        return;
      }

      if (msg.event === 'media') {
        const pcm = muLawToPcm16(Buffer.from(msg.media.payload, 'base64'));
        const { started, utterance } = detector.push(pcm);

        if (started && speaking) {
          speechEpoch += 1; // invalidate the reply being streamed
          speaking = false;
          clearPlayback();
        }
        if (utterance) void onUtterance(utterance);
        return;
      }

      if (msg.event === 'stop') {
        closed = true;
      }
    } catch (err) {
      console.error('[bridge] stream message error:', err.message);
    }
  });

  ws.on('close', () => {
    closed = true;
    detector.reset();
  });
}
