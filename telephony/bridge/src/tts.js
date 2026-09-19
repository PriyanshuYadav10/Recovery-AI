import { config } from './config.js';
import { wavToTwilioMuLaw } from './audio.js';

/**
 * Text to speech, returning mu-law 8kHz ready for a Twilio media stream.
 *
 * Groq Orpheus is preferred for the same reason as Whisper - one vendor, one
 * key. Orpheus is gated behind terms acceptance on the Groq console; until that
 * is accepted the API answers 400, so the error is surfaced plainly rather than
 * being swallowed into silence on the call.
 */

class GroqSpeech {
  name = 'groq-orpheus';

  constructor() {
    if (!config.groqApiKey) throw new Error('TTS_PROVIDER=groq needs GROQ_API_KEY');
  }

  async synthesize(text) {
    const res = await fetch('https://api.groq.com/openai/v1/audio/speech', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${config.groqApiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: config.groqTtsModel,
        input: text,
        voice: config.groqTtsVoice,
        response_format: 'wav'
      })
    });

    if (!res.ok) {
      const body = (await res.text()).slice(0, 200);
      if (res.status === 400 && body.includes('terms')) {
        throw new Error(
          `${config.groqTtsModel} needs terms acceptance at console.groq.com before it will ` +
            'speak. Accept them, or set TTS_PROVIDER=elevenlabs.'
        );
      }
      throw new Error(`Groq TTS HTTP ${res.status}: ${body}`);
    }

    return wavToTwilioMuLaw(Buffer.from(await res.arrayBuffer()));
  }
}

class ElevenLabsSpeech {
  name = 'elevenlabs';

  constructor() {
    if (!config.elevenlabsApiKey || !config.elevenlabsVoiceId) {
      throw new Error('TTS_PROVIDER=elevenlabs needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID');
    }
  }

  async synthesize(text) {
    // ElevenLabs can emit mu-law 8k directly, so no conversion is needed.
    const res = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${config.elevenlabsVoiceId}?output_format=ulaw_8000`,
      {
        method: 'POST',
        headers: {
          'xi-api-key': config.elevenlabsApiKey,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text, model_id: 'eleven_turbo_v2' })
      }
    );
    if (!res.ok) {
      throw new Error(`ElevenLabs HTTP ${res.status}: ${(await res.text()).slice(0, 160)}`);
    }
    return Buffer.from(await res.arrayBuffer());
  }
}

export function createTts() {
  return config.ttsProvider === 'elevenlabs' ? new ElevenLabsSpeech() : new GroqSpeech();
}
