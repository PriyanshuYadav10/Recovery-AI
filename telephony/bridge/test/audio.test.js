import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  muLawDecodeSample,
  muLawEncodeSample,
  muLawToPcm16,
  pcm16ToMuLaw,
  pcm16ToWav,
  wavToPcm16,
  resample,
  wavToTwilioMuLaw,
  SpeechDetector
} from '../src/audio.js';

test('mu-law round trip stays close to the original sample', () => {
  // mu-law is lossy by design; what matters is that the error stays small
  // relative to amplitude, not that it is zero.
  for (const value of [0, 100, -100, 1000, -1000, 8000, -8000, 25000, -25000]) {
    const decoded = muLawDecodeSample(muLawEncodeSample(value));
    const tolerance = Math.max(64, Math.abs(value) * 0.08);
    assert.ok(
      Math.abs(decoded - value) <= tolerance,
      `${value} -> ${decoded} exceeded tolerance ${tolerance}`
    );
    assert.equal(Math.sign(decoded), Math.sign(value), 'sign must survive');
  }
});

test('mu-law encoding clips instead of wrapping', () => {
  const loud = muLawDecodeSample(muLawEncodeSample(32767));
  const quiet = muLawDecodeSample(muLawEncodeSample(-32768));
  assert.ok(loud > 30000, 'positive clip should stay positive and loud');
  assert.ok(quiet < -30000, 'negative clip should stay negative and loud');
});

test('buffer helpers preserve length', () => {
  const samples = Int16Array.from([0, 500, -500, 12000, -12000]);
  const encoded = pcm16ToMuLaw(samples);
  assert.equal(encoded.length, samples.length);
  assert.equal(muLawToPcm16(encoded).length, samples.length);
});

test('WAV round trip returns the same samples and rate', () => {
  const samples = Int16Array.from([0, 1000, -1000, 32000, -32000, 7]);
  const { samples: back, sampleRate } = wavToPcm16(pcm16ToWav(samples, 16000));
  assert.equal(sampleRate, 16000);
  assert.deepEqual(Array.from(back), Array.from(samples));
});

test('WAV reader skips unexpected chunks rather than reading them as audio', () => {
  const samples = Int16Array.from([1, 2, 3, 4]);
  const real = pcm16ToWav(samples, 8000);

  // Splice a LIST chunk between fmt and data, as some encoders do.
  const list = Buffer.alloc(8 + 4);
  list.write('LIST', 0);
  list.writeUInt32LE(4, 4);
  list.write('INFO', 8);

  const spliced = Buffer.concat([real.subarray(0, 36), list, real.subarray(36)]);
  spliced.writeUInt32LE(spliced.length - 8, 4);

  const { samples: back } = wavToPcm16(spliced);
  assert.deepEqual(Array.from(back), Array.from(samples));
});

test('stereo WAV is downmixed to mono', () => {
  // Hand-build a 2-channel WAV: frames (100,200) and (300,400).
  const interleaved = Int16Array.from([100, 200, 300, 400]);
  const wav = pcm16ToWav(interleaved, 8000);
  wav.writeUInt16LE(2, 22); // channels = 2
  const { samples } = wavToPcm16(wav);
  assert.deepEqual(Array.from(samples), [150, 350]);
});

test('resample halves and doubles the sample count', () => {
  const samples = Int16Array.from({ length: 100 }, (_, i) => i * 100);
  assert.equal(resample(samples, 16000, 8000).length, 50);
  assert.equal(resample(samples, 8000, 16000).length, 200);
  assert.equal(resample(samples, 8000, 8000), samples, 'same rate should be a no-op');
});

test('a 24kHz TTS wav becomes 8kHz mu-law for Twilio', () => {
  const samples = Int16Array.from({ length: 2400 }, (_, i) =>
    Math.round(8000 * Math.sin((2 * Math.PI * 440 * i) / 24000))
  );
  const mulaw = wavToTwilioMuLaw(pcm16ToWav(samples, 24000));
  assert.equal(mulaw.length, 800, '100ms at 8kHz is 800 mu-law bytes');
});

test('SpeechDetector emits an utterance after trailing silence', () => {
  const detector = new SpeechDetector({ threshold: 500, silenceMs: 100, minSpeechMs: 40 });
  const loud = Int16Array.from({ length: 800 }, (_, i) => (i % 2 ? 6000 : -6000));
  const quiet = new Int16Array(800); // 100ms of silence

  const first = detector.push(loud);
  assert.equal(first.started, true, 'speech should be detected');
  assert.equal(first.utterance, null, 'not finished while still talking');

  const second = detector.push(quiet);
  assert.ok(second.utterance, 'silence should close the utterance');
  assert.ok(second.utterance.length >= 800, 'captured audio should include the speech');
});

test('SpeechDetector ignores a blip too short to be speech', () => {
  const detector = new SpeechDetector({ threshold: 500, silenceMs: 100, minSpeechMs: 300 });
  detector.push(Int16Array.from({ length: 160 }, () => 6000)); // 20ms only
  const { utterance } = detector.push(new Int16Array(1600)); // 200ms of silence
  assert.equal(utterance, null, 'a 20ms blip must not be sent to the transcriber');
});

test('SpeechDetector stays quiet through background noise', () => {
  const detector = new SpeechDetector({ threshold: 2000, silenceMs: 100 });
  const hiss = Int16Array.from({ length: 4000 }, () => Math.round((Math.random() - 0.5) * 200));
  const { started, utterance } = detector.push(hiss);
  assert.equal(started, false);
  assert.equal(utterance, null);
});
