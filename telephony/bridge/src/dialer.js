import twilio from 'twilio';
import { config, assertTwilioReady } from './config.js';

let _client = null;

/** Built on first use so the module imports cleanly without credentials. */
export function client() {
  if (!_client) {
    assertTwilioReady();
    _client = twilio(config.twilio.accountSid, config.twilio.authToken);
  }
  return _client;
}

/**
 * Place the outbound recovery call.
 *
 * The DNC gate has already run in the brain before this is reached - the Python
 * adapter only calls /dial once ConversationManager.start has cleared the lead.
 */
export async function dial({ to, callId, leadId }) {
  if (!config.publicBaseUrl) {
    throw new Error('PUBLIC_BASE_URL is required so Twilio can reach the webhooks.');
  }
  const qs = new URLSearchParams({ callId: callId || '', leadId: leadId || '' }).toString();

  const call = await client().calls.create({
    to,
    from: config.twilio.phoneNumber,
    url: `${config.publicBaseUrl}/twiml/answer?${qs}`,
    statusCallback: `${config.publicBaseUrl}/twiml/status?${qs}`,
    statusCallbackMethod: 'POST',
    statusCallbackEvent: ['initiated', 'answered', 'completed'],
    machineDetection: config.twilio.machineDetection,
    machineDetectionTimeout: config.twilio.amdTimeout,
    record: config.twilio.record
  });

  return { callSid: call.sid, status: call.status, to };
}

/**
 * Warm transfer. The customer stays on the line; Twilio re-issues TwiML that
 * dials the human queue. Everything collected is already waiting in the Agent
 * Inbox, so the human opens with context instead of questions.
 */
export async function transfer({ callSid, target }) {
  const destination = target || config.humanQueueNumber;
  if (!destination) {
    return { status: 'transfer_unconfigured', error: 'HUMAN_QUEUE_NUMBER is not set' };
  }
  const response = new twilio.twiml.VoiceResponse();
  response.say(
    { language: config.language },
    'Connecting you to a colleague now. They can already see everything you have told me.'
  );
  const dialVerb = response.dial({ answerOnBridge: true });
  dialVerb.number(destination);

  await client().calls(callSid).update({ twiml: response.toString() });
  return { status: 'transferred', callSid, target: destination };
}

export async function hangup(callSid) {
  await client().calls(callSid).update({ status: 'completed' });
  return { status: 'ended', callSid };
}
