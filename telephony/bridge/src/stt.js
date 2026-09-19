import { config } from './config.js';
import { pcm16ToWav } from './audio.js';

/**
 * Speech to text.
 *
 * Groq Whisper is the default: the account already has a Groq key for the
 * reasoning model, so it removes a second vendor. Deepgram remains available
 * because it streams, which Whisper does not - with Whisper the bridge does its
 * own endpointing (see SpeechDetector) and transcribes a whole utterance.
 */

class GroqWhisper {
  name = 'groq-whisper';

  constructor() {
    if (!config.groqApiKey) {
      throw new Error('STT_PROVIDER=groq needs GROQ_API_KEY');
    }
  }

  /** @param {Int16Array} samples 8kHz mono PCM */
  async transcribe(samples) {
    const wav = pcm16ToWav(samples, 8000);
    const form = new FormData();
    form.append('file', new Blob([wav], { type: 'audio/wav' }), 'utterance.wav');
    form.append('model', config.groqSttModel);
    form.append('language', config.language.split('-')[0] || 'en');
    form.append('response_format', 'json');
    // Priming the decoder with domain words measurably helps on 8kHz phone
    // audio, where supplier names are the most misheard field.
    form.append(
      'prompt',
      'Australian energy comparison call. Possible words: postcode, AGL, Origin, ' +
        'EnergyAustralia, Red Energy, Alinta, electricity, gas, solar, townhouse.'
    );

    const res = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${config.groqApiKey}` },
      body: form
    });

    if (!res.ok) {
      throw new Error(`Groq STT HTTP ${res.status}: ${(await res.text()).slice(0, 160)}`);
    }
    const data = await res.json();
    return (data.text || '').trim();
  }
}

class DeepgramStt {
  name = 'deepgram';

  constructor() {
    if (!config.deepgramApiKey) {
      throw new Error('STT_PROVIDER=deepgram needs DEEPGRAM_API_KEY');
    }
  }

  async transcribe(samples) {
    const wav = pcm16ToWav(samples, 8000);
    const res = await fetch(
      'https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language=' +
        encodeURIComponent(config.language),
      {
        method: 'POST',
        headers: {
          Authorization: `Token ${config.deepgramApiKey}`,
          'Content-Type': 'audio/wav'
        },
        body: wav
      }
    );
    if (!res.ok) {
      throw new Error(`Deepgram HTTP ${res.status}: ${(await res.text()).slice(0, 160)}`);
    }
    const data = await res.json();
    return (data.results?.channels?.[0]?.alternatives?.[0]?.transcript || '').trim();
  }
}

export function createStt() {
  return config.sttProvider === 'deepgram' ? new DeepgramStt() : new GroqWhisper();
}
