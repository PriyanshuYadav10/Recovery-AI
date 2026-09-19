import 'dotenv/config';

/**
 * Credentials are read, not demanded, at import time. Requiring them here made
 * the audio and STT modules unimportable - and untestable - without a Twilio
 * account, even though they never touch Twilio. Each subsystem asserts what it
 * needs, when it needs it.
 */
function env(name, fallback = '') {
  return process.env[name] || fallback;
}

export const config = {
  port: Number(process.env.PORT || 3100),
  publicBaseUrl: process.env.PUBLIC_BASE_URL || '',
  recoveryApiUrl: (process.env.RECOVERY_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, ''),
  pipeline: (process.env.VOICE_PIPELINE || 'gather').toLowerCase(),
  humanQueueNumber: process.env.HUMAN_QUEUE_NUMBER || '',
  twilio: {
    accountSid: env('TWILIO_ACCOUNT_SID'),
    authToken: env('TWILIO_AUTH_TOKEN'),
    phoneNumber: env('TWILIO_PHONE_NUMBER'),
    machineDetection: process.env.TWILIO_MACHINE_DETECTION || 'Enable',
    amdTimeout: Number(process.env.TWILIO_AMD_TIMEOUT || 30),
    record: String(process.env.TWILIO_RECORD || 'true') === 'true'
  },
  // Audio providers. Groq is the default for both, because the brain already
  // needs a Groq key - one vendor instead of three.
  sttProvider: (process.env.STT_PROVIDER || 'groq').toLowerCase(),
  ttsProvider: (process.env.TTS_PROVIDER || 'groq').toLowerCase(),
  groqApiKey: process.env.GROQ_API_KEY || '',
  groqSttModel: process.env.GROQ_STT_MODEL || 'whisper-large-v3-turbo',
  groqTtsModel: process.env.GROQ_TTS_MODEL || 'canopylabs/orpheus-v1-english',
  groqTtsVoice: process.env.GROQ_TTS_VOICE || 'tara',

  deepgramApiKey: process.env.DEEPGRAM_API_KEY || '',
  elevenlabsApiKey: process.env.ELEVENLABS_API_KEY || '',
  elevenlabsVoiceId: process.env.ELEVENLABS_VOICE_ID || '',
  language: process.env.SPEECH_LANGUAGE || 'en-AU'
};

/** Called by the parts that actually place calls. */
export function assertTwilioReady() {
  const missing = ['accountSid', 'authToken', 'phoneNumber'].filter((k) => !config.twilio[k]);
  if (missing.length) {
    const names = missing.map((k) => `TWILIO_${k.replace(/[A-Z]/g, (c) => '_' + c).toUpperCase()}`);
    throw new Error(
      `Missing Twilio credentials: ${names.join(', ')}. Copy .env.example to .env and fill it in.`
    );
  }
}

export function assertPipelineReady() {
  if (config.pipeline === 'stream') {
    const missing = [];
    if (config.sttProvider === 'groq' && !config.groqApiKey) missing.push('GROQ_API_KEY (STT)');
    if (config.sttProvider === 'deepgram' && !config.deepgramApiKey) missing.push('DEEPGRAM_API_KEY');
    if (config.ttsProvider === 'groq' && !config.groqApiKey) missing.push('GROQ_API_KEY (TTS)');
    if (config.ttsProvider === 'elevenlabs' && !(config.elevenlabsApiKey && config.elevenlabsVoiceId)) {
      missing.push('ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID');
    }
    if (missing.length) {
      throw new Error(
        `VOICE_PIPELINE=stream needs ${missing.join(', ')}. ` +
          'Set VOICE_PIPELINE=gather to run on Twilio ASR/TTS alone.'
      );
    }
  }
  if (!config.publicBaseUrl) {
    console.warn('[bridge] PUBLIC_BASE_URL is not set - Twilio cannot reach the webhooks.');
  }
}
