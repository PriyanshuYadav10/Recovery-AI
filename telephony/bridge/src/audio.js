/**
 * Audio plumbing for the Twilio media-stream pipeline.
 *
 * Twilio speaks G.711 mu-law at 8kHz. Whisper wants a container it can decode,
 * and TTS providers hand back whatever sample rate they like. Everything needed
 * to move between those worlds lives here, with no dependencies, so it can be
 * unit tested without a phone call.
 */

const MULAW_BIAS = 0x84;
const MULAW_CLIP = 32635;

/** Decode one mu-law byte to a signed 16-bit sample. */
export function muLawDecodeSample(byte) {
  const u = ~byte & 0xff;
  const sign = u & 0x80;
  const exponent = (u >> 4) & 0x07;
  const mantissa = u & 0x0f;
  let sample = ((mantissa << 3) + MULAW_BIAS) << exponent;
  sample -= MULAW_BIAS;
  return sign ? -sample : sample;
}

/** Encode a signed 16-bit sample to one mu-law byte. */
export function muLawEncodeSample(sample) {
  let sign = (sample >> 8) & 0x80;
  if (sign) sample = -sample;
  if (sample > MULAW_CLIP) sample = MULAW_CLIP;
  sample += MULAW_BIAS;

  let exponent = 7;
  for (let mask = 0x4000; (sample & mask) === 0 && exponent > 0; exponent--, mask >>= 1);

  const mantissa = (sample >> (exponent + 3)) & 0x0f;
  return ~(sign | (exponent << 4) | mantissa) & 0xff;
}

/** mu-law buffer -> Int16Array of PCM samples. */
export function muLawToPcm16(buffer) {
  const out = new Int16Array(buffer.length);
  for (let i = 0; i < buffer.length; i++) out[i] = muLawDecodeSample(buffer[i]);
  return out;
}

/** Int16Array of PCM samples -> mu-law buffer. */
export function pcm16ToMuLaw(samples) {
  const out = Buffer.allocUnsafe(samples.length);
  for (let i = 0; i < samples.length; i++) out[i] = muLawEncodeSample(samples[i]);
  return out;
}

/** Wrap PCM16 samples in a minimal mono WAV container. */
export function pcm16ToWav(samples, sampleRate = 8000) {
  const dataBytes = samples.length * 2;
  const buffer = Buffer.alloc(44 + dataBytes);

  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataBytes, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16); // PCM header size
  buffer.writeUInt16LE(1, 20); // format: PCM
  buffer.writeUInt16LE(1, 22); // channels: mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28); // byte rate
  buffer.writeUInt16LE(2, 32); // block align
  buffer.writeUInt16LE(16, 34); // bits per sample
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataBytes, 40);

  for (let i = 0; i < samples.length; i++) buffer.writeInt16LE(samples[i], 44 + i * 2);
  return buffer;
}

/**
 * Read a PCM WAV produced by a TTS provider. Chunks are walked rather than
 * assumed at fixed offsets, because providers emit LIST/fact chunks that would
 * otherwise be read as audio and come out as noise.
 */
export function wavToPcm16(buffer) {
  if (buffer.length < 12 || buffer.toString('ascii', 0, 4) !== 'RIFF') {
    throw new Error('not a RIFF/WAV buffer');
  }

  let offset = 12;
  let sampleRate = 8000;
  let channels = 1;
  let bitsPerSample = 16;
  let data = null;

  while (offset + 8 <= buffer.length) {
    const id = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    const body = offset + 8;

    if (id === 'fmt ') {
      channels = buffer.readUInt16LE(body + 2);
      sampleRate = buffer.readUInt32LE(body + 4);
      bitsPerSample = buffer.readUInt16LE(body + 14);
    } else if (id === 'data') {
      data = buffer.subarray(body, Math.min(body + size, buffer.length));
      break;
    }
    offset = body + size + (size % 2); // chunks are word aligned
  }

  if (!data) throw new Error('no data chunk in WAV');
  if (bitsPerSample !== 16) throw new Error(`unsupported bit depth: ${bitsPerSample}`);

  const total = Math.floor(data.length / 2);
  const interleaved = new Int16Array(total);
  for (let i = 0; i < total; i++) interleaved[i] = data.readInt16LE(i * 2);

  if (channels === 1) return { samples: interleaved, sampleRate };

  // Downmix to mono - the phone leg is mono.
  const frames = Math.floor(total / channels);
  const mono = new Int16Array(frames);
  for (let i = 0; i < frames; i++) {
    let sum = 0;
    for (let c = 0; c < channels; c++) sum += interleaved[i * channels + c];
    mono[i] = Math.round(sum / channels);
  }
  return { samples: mono, sampleRate };
}

/** Linear resample. Good enough for 8kHz telephony speech. */
export function resample(samples, fromRate, toRate) {
  if (fromRate === toRate) return samples;
  const ratio = fromRate / toRate;
  const length = Math.floor(samples.length / ratio);
  const out = new Int16Array(length);

  for (let i = 0; i < length; i++) {
    const position = i * ratio;
    const index = Math.floor(position);
    const frac = position - index;
    const a = samples[index] ?? 0;
    const b = samples[index + 1] ?? a;
    out[i] = Math.round(a + (b - a) * frac);
  }
  return out;
}

/** Any TTS WAV -> the mu-law 8kHz Twilio expects on a media stream. */
export function wavToTwilioMuLaw(wavBuffer) {
  const { samples, sampleRate } = wavToPcm16(wavBuffer);
  return pcm16ToMuLaw(resample(samples, sampleRate, 8000));
}

/**
 * Energy-based endpointing.
 *
 * Whisper is not a streaming API, so something has to decide when the caller
 * has finished a sentence. Deepgram gave us that for free; this replaces it.
 * Speech starts when short-term energy crosses the threshold and ends after a
 * run of quiet frames, which is also what triggers barge-in.
 */
export class SpeechDetector {
  constructor({
    threshold = 900,
    silenceMs = 700,
    minSpeechMs = 250,
    frameMs = 20,
    sampleRate = 8000,
  } = {}) {
    this.threshold = threshold;
    this.silenceFrames = Math.ceil(silenceMs / frameMs);
    this.minSpeechFrames = Math.ceil(minSpeechMs / frameMs);
    this.frameSize = Math.round((sampleRate * frameMs) / 1000);

    this.speaking = false;
    this.speechFrames = 0;
    this.quietFrames = 0;
    this.buffer = [];
    this.pending = [];
  }

  static rms(samples) {
    if (!samples.length) return 0;
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
  }

  /**
   * Feed PCM16 samples.
   * @returns {{started: boolean, utterance: Int16Array|null}}
   */
  push(samples) {
    let started = false;
    let utterance = null;

    for (const sample of samples) this.pending.push(sample);

    while (this.pending.length >= this.frameSize) {
      const frame = Int16Array.from(this.pending.splice(0, this.frameSize));
      const loud = SpeechDetector.rms(frame) >= this.threshold;

      if (loud) {
        if (!this.speaking) {
          this.speaking = true;
          this.speechFrames = 0;
          this.buffer = [];
          started = true;
        }
        this.speechFrames++;
        this.quietFrames = 0;
        this.buffer.push(frame);
      } else if (this.speaking) {
        this.quietFrames++;
        this.buffer.push(frame); // keep trailing quiet so words are not clipped
        if (this.quietFrames >= this.silenceFrames) {
          const enough = this.speechFrames >= this.minSpeechFrames;
          const collected = enough ? this._flatten() : null;
          this.reset();
          if (collected) utterance = collected;
        }
      }
    }

    return { started, utterance };
  }

  _flatten() {
    const total = this.buffer.reduce((n, f) => n + f.length, 0);
    const out = new Int16Array(total);
    let offset = 0;
    for (const frame of this.buffer) {
      out.set(frame, offset);
      offset += frame.length;
    }
    return out;
  }

  reset() {
    this.speaking = false;
    this.speechFrames = 0;
    this.quietFrames = 0;
    this.buffer = [];
  }
}
