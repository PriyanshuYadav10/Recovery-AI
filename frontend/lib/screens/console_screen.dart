import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';
import '../services/api_client.dart';
import '../services/browser_voice.dart';
import '../widgets/handoff_overlay.dart';

class ConsoleScreen extends StatefulWidget {
  const ConsoleScreen({super.key});

  @override
  State<ConsoleScreen> createState() => _ConsoleScreenState();
}

class _ConsoleScreenState extends State<ConsoleScreen> {
  final api = ApiClient();
  final voice = BrowserVoiceService();
  final inputCtrl = TextEditingController();
  final scrollCtrl = ScrollController();

  String? callId;
  Map<String, dynamic> snapshot = {};
  Map<String, dynamic> turn = {};
  List<Map<String, dynamic>> transcript = [];
  List<String> demoQueue = [];
  bool busy = false;
  bool live = false;
  bool showDemoControls = false;
  bool watchingRealCall = false;
  String? banner;
  StreamSubscription? _voiceSub;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _voiceSub = voice.utterances.listen((t) {
      if (t.isNotEmpty) _send(t);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  Future<void> _bootstrap() async {
    final args = ModalRoute.of(context)?.settings.arguments as Map?;
    if (args == null) return;
    final watchId = args['callId'] as String?;
    if (watchId != null && args['watch'] == true) {
      await _watchRealCall(watchId);
      return;
    }
    final scenario = args['scenario'] as String?;
    final leadId = args['leadId'] as String? ?? 'EN-1001';
    if (args['autoStart'] == true) {
      await _start(leadId: leadId, scenario: scenario);
    }
  }

  /// Attaches to a call already ringing on a real phone (dialled from the
  /// landing page's REAL PHONE CALL panel) instead of starting a new one.
  /// The customer's speech reaches the brain through the Twilio bridge, not
  /// through this screen - so this only ever polls and displays, it never
  /// sends utterances itself.
  Future<void> _watchRealCall(String id) async {
    setState(() {
      callId = id;
      watchingRealCall = true;
      live = true;
      busy = true;
      banner = null;
    });
    await _pollRealCall();
    setState(() => busy = false);
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _pollRealCall());
  }

  Future<void> _pollRealCall() async {
    if (callId == null || !mounted) return;
    try {
      final snap = await api.getCall(callId!);
      if (!mounted) return;
      setState(() {
        snapshot = snap;
        turn = {
          'state': snap['state'],
          'radar': snap['radar'],
          'journey_progress': snap['recovery'],
          'escalated': snap['state'] == 'HANDOFF',
          'handoff_brief': snap['handoff_brief'],
          'ended': snap['state'] == 'ENDED',
          'receipt': snap['receipt'],
          'handoff_ticket_id': snap['handoff_ticket_id'],
        };
        _ingestTranscript(snap);
        banner = null;
      });
      if (snap['state'] == 'ENDED' || snap['state'] == 'HANDOFF') {
        _pollTimer?.cancel();
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (scrollCtrl.hasClients) {
          scrollCtrl.animateTo(scrollCtrl.position.maxScrollExtent,
              duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
        }
      });
    } catch (e) {
      if (mounted) setState(() => banner = 'Lost contact with the call  -  $e');
    }
  }

  Future<void> _start({required String leadId, String? scenario}) async {
    setState(() {
      busy = true;
      banner = null;
      transcript = [];
    });
    try {
      final res = await api.startCall(
        leadId: leadId,
        voiceMode: 'BROWSER',
        scenario: scenario,
      );
      callId = res['call_id'] as String;
      turn = (res['turn'] as Map).cast<String, dynamic>();
      snapshot = (res['snapshot'] as Map).cast<String, dynamic>();
      _ingestTranscript(snapshot);
      final utts = res['scenario_utterances'];
      demoQueue = utts is List ? utts.map((e) => '$e').toList() : <String>[];
      live = true;
      voice.speak(turn['assistant_message']?.toString() ?? '');
      if (scenario != null && demoQueue.isNotEmpty) {
        // Auto-advance demo after a short beat for judges
        unawaited(_autoDemo());
      }
    } catch (e) {
      setState(() => banner = 'AI provider / backend issue  -  $e');
    } finally {
      setState(() => busy = false);
    }
  }

  Future<void> _autoDemo() async {
    while (demoQueue.isNotEmpty && mounted && live) {
      await Future.delayed(const Duration(milliseconds: 1400));
      if (!mounted || demoQueue.isEmpty) break;
      final next = demoQueue.removeAt(0);
      await _send(next, fromDemo: true);
      if (turn['ended'] == true) break;
    }
  }

  void _ingestTranscript(Map<String, dynamic> snap) {
    final t = snap['transcript'];
    if (t is List) {
      transcript = t.map((e) => (e as Map).cast<String, dynamic>()).toList();
    }
  }

  Future<void> _send(String text, {bool fromDemo = false, double conf = 0.95}) async {
    if (callId == null || text.trim().isEmpty || busy) return;
    setState(() => busy = true);
    try {
      final res = await api.utterance(callId: callId!, text: text.trim(), speechConfidence: conf);
      turn = (res['turn'] as Map).cast<String, dynamic>();
      snapshot = (res['snapshot'] as Map).cast<String, dynamic>();
      _ingestTranscript(snapshot);
      inputCtrl.clear();
      voice.speak(turn['assistant_message']?.toString() ?? '');
      if (turn['escalated'] == true && turn['handoff_brief'] != null) {
        await Future.delayed(const Duration(milliseconds: 400));
        if (mounted) {
          await showHandoffOverlay(context, turn['handoff_brief'] as Map<String, dynamic>, snapshot);
        }
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (scrollCtrl.hasClients) {
          scrollCtrl.animateTo(
            scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeOut,
          );
        }
      });
    } catch (e) {
      setState(() => banner = 'Turn failed  -  $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _voiceSub?.cancel();
    voice.dispose();
    inputCtrl.dispose();
    scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lead = (snapshot['lead'] as Map?)?.cast<String, dynamic>() ?? {};
    final radar = (snapshot['radar'] as Map?)?.cast<String, dynamic>() ??
        (turn['radar'] as Map?)?.cast<String, dynamic>() ??
        {};
    final progress = (turn['journey_progress'] as List?) ??
        ((snapshot['recovery'] as Map?)?['missing_fields'] as List?) ??
        [];
    final fields = (turn['extracted_fields'] as Map?)?.cast<String, dynamic>() ??
        (snapshot['fields'] as Map?)?.cast<String, dynamic>() ??
        {};
    final audit = (turn['audit_tail'] as List?) ?? (snapshot['audit'] as List?) ?? [];
    final why = turn['why'] as Map? ?? (snapshot['why'] is List && (snapshot['why'] as List).isNotEmpty
        ? (snapshot['why'] as List).last
        : null);
    final conf = (turn['confidence'] as Map?)?.cast<String, dynamic>();
    final state = turn['state']?.toString() ?? snapshot['state']?.toString() ?? 'IDLE';
    final mood = radar['customer_mood']?.toString() ?? 'Neutral';

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFF0B1220), Color(0xFF101A2E), Color(0xFF0B1220)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _header(state, radar),
              if (banner != null)
                Container(
                  width: double.infinity,
                  color: AppTheme.warn.withValues(alpha: 0.15),
                  padding: const EdgeInsets.all(10),
                  child: Text(banner!, style: const TextStyle(color: AppTheme.warn)),
                ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Expanded(flex: 2, child: _leadPanel(lead, snapshot)),
                      const SizedBox(width: 12),
                      Expanded(flex: 4, child: _transcriptPanel()),
                      const SizedBox(width: 12),
                      Expanded(flex: 3, child: _aiPanel(state, fields, conf, why, radar, mood)),
                    ],
                  ),
                ),
              ),
              _journeyBar(progress),
              _receiptBar(),
              _timeline(audit),
              _demoControls(),
              _composer(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header(String state, Map radar) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back_ios_new, size: 16),
          ),
          Text('CIMET.', style: AppTheme.heading(15)),
          const SizedBox(width: 6),
          Text('/ recovery ai', style: AppTheme.prose(13).copyWith(color: AppTheme.muted)),
          const SizedBox(width: 18),
          _pill(live ? 'LIVE' : 'IDLE', live ? AppTheme.accent : AppTheme.panelAlt),
          const SizedBox(width: 8),
          if (watchingRealCall)
            _pill('☎ REAL PHONE CALL', AppTheme.accent)
          else
            _pill('VOICE · BROWSER', AppTheme.panelAlt),
          const SizedBox(width: 8),
          _pill(state, AppTheme.panelAlt),
          const Spacer(),
          const MonoLabel('AI CALL RADAR', size: 9.5),
        ],
      ),
    );
  }

  Widget _leadPanel(Map lead, Map snap) {
    final recovery = (snap['recovery'] as Map?) ?? {};
    return _panel(
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          Text('LEAD', style: _section()),
          const SizedBox(height: 8),
          Text('${lead['first_name'] ?? '-'} ${lead['last_name'] ?? ''}',
              style: AppTheme.heading(21)),
          Text('Energy · ${lead['lead_id'] ?? ''}', style: const TextStyle(color: AppTheme.muted)),
          const SizedBox(height: 16),
          Text('RECOVERY CONTEXT', style: _section()),
          const SizedBox(height: 8),
          _kv('Last completed', '${recovery['last_completed_step'] ?? '-'}'),
          _kv('Objective', '${recovery['recovery_objective'] ?? '-'}'),
          const SizedBox(height: 8),
          Text('Already known', style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
          ...(recovery['previously_known_fields'] as List? ?? []).map((e) => Text('· $e', style: AppTheme.prose(12.5).copyWith(color: AppTheme.accent))),
          const SizedBox(height: 8),
          Text('Still required', style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
          ...(recovery['missing_fields'] as List? ?? []).map((e) => Text('· $e', style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted))),
          const SizedBox(height: 16),
          Text('AI CALL RADAR', style: _section()),
          const SizedBox(height: 8),
          _radarBlock((snap['radar'] as Map?)?.cast<String, dynamic>() ??
              (turn['radar'] as Map?)?.cast<String, dynamic>() ??
              {}),
        ],
      ),
    );
  }

  Widget _radarBlock(Map radar) {
    final conf = ((radar['confidence'] ?? 0.9) as num).toDouble();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _kv('Mood', '${radar['customer_mood'] ?? 'Neutral'}'),
        const SizedBox(height: 6),
        Text('CONFIDENCE  ${(conf * 100).round()}%', style: const TextStyle(fontSize: 12, color: AppTheme.muted)),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: conf.clamp(0, 1),
            minHeight: 8,
            backgroundColor: Colors.white12,
            color: AppTheme.accent,
          ),
        ),
        const SizedBox(height: 8),
        _kv('Health', '${radar['conversation_health'] ?? '-'}'),
        _kv('Interruptions', '${radar['interruptions'] ?? 0}'),
        _kv('Clarifications', '${radar['clarifications'] ?? 0}'),
        _kv('Fields', '${radar['fields_captured'] ?? '-'}'),
        _kv('Escalation risk', '${radar['escalation_risk'] ?? 'Low'}'),
        if (radar['handoff_phase'] != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              '${radar['handoff_phase']}',
              style: const TextStyle(color: AppTheme.danger, fontWeight: FontWeight.w700),
            ),
          ),
      ],
    );
  }

  Widget _transcriptPanel() {
    return _panel(
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppTheme.line)),
            ),
            child: Row(
              children: [
                const MonoLabel('RECOVERY CALL · TRANSCRIPT'),
                const Spacer(),
                if (busy)
                  const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2))
                else if (live) ...[
                  Container(
                    width: 7,
                    height: 7,
                    decoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 7),
                  const MonoLabel('REC', color: AppTheme.accent, size: 9),
                ],
              ],
            ),
          ),
          Expanded(
            child: ListView.builder(
              controller: scrollCtrl,
              padding: const EdgeInsets.all(14),
              itemCount: transcript.length,
              itemBuilder: (_, i) {
                final m = transcript[i];
                final role = '${m['role']}';
                final isAi = role == 'assistant';
                // Speaker tags run inline in mono caps, the way the handout
                // sets a call transcript - no chat bubbles.
                final tag = isAi
                    ? 'AI AGENT'
                    : role == 'human_agent'
                        ? 'HUMAN'
                        : 'CUSTOMER';
                final tagColour = isAi
                    ? AppTheme.accent
                    : role == 'human_agent'
                        ? AppTheme.text
                        : AppTheme.muted;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      MonoLabel(tag, color: tagColour, size: 9),
                      const SizedBox(height: 5),
                      Text(
                        '${m['text']}',
                        style: AppTheme.prose(13.5).copyWith(
                          color: isAi ? AppTheme.text : AppTheme.body,
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _aiPanel(String state, Map fields, Map? conf, dynamic why, Map radar, String mood) {
    return _panel(
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          Text('AI STATE', style: _section()),
          const SizedBox(height: 8),
          Text(state, style: AppTheme.figure(18, color: AppTheme.accent)),
          _kv('Intent', '${turn['intent'] ?? '-'}'),
          _kv('Mood', mood),
          if (conf != null) ...[
            const SizedBox(height: 8),
            Text('Confidence ${( ((conf['speech_confidence']??1)+(conf['intent_confidence']??1)+(conf['field_confidence']??1)+(conf['journey_confidence']??1))/4 * 100).round()}%',
                style: const TextStyle(color: AppTheme.muted)),
          ],
          const SizedBox(height: 14),
          Text('EXTRACTED FIELDS', style: _section()),
          const SizedBox(height: 8),
          ...fields.entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle, size: 14, color: AppTheme.accent),
                    const SizedBox(width: 6),
                    Expanded(child: Text('${e.key}: ${e.value}')),
                  ],
                ),
              )),
          const SizedBox(height: 14),
          Text('WHY DID AI DO THAT?', style: _section()),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.03),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.white10),
            ),
            child: Text(
              why == null ? 'Awaiting action...' : '${why['action']}: ${why['reason']}',
              style: const TextStyle(height: 1.4, color: AppTheme.text),
            ),
          ),
        ],
      ),
    );
  }

  Widget _journeyBar(List progress) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(color: AppTheme.panel.withValues(alpha: 0.7), border: const Border(top: BorderSide(color: Colors.white10))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('JOURNEY', style: _section()),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final raw in progress)
                  Builder(builder: (_) {
                    final p = raw is Map ? raw.cast<String, dynamic>() : <String, dynamic>{'id': raw, 'status': 'pending'};
                    final status = '${p['status']}';
                    final color = status == 'done'
                        ? AppTheme.accent
                        : status == 'active'
                            ? AppTheme.warn
                            : AppTheme.muted;
                    return Padding(
                      padding: const EdgeInsets.only(right: 14),
                      child: Row(
                        children: [
                          Icon(status == 'done' ? Icons.check_circle : Icons.circle, size: 12, color: color),
                          const SizedBox(width: 4),
                          Text('${p['label'] ?? p['id']}', style: TextStyle(color: color, fontSize: 12)),
                        ],
                      ),
                    );
                  }),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Proof the journey actually landed: the reference the completion sandbox
  /// issued, or the reason it refused the payload.
  Widget _receiptBar() {
    final receipt = (turn['receipt'] as Map?) ?? (snapshot['receipt'] as Map?);
    final ticketId = turn['handoff_ticket_id'] ?? snapshot['handoff_ticket_id'];
    if (receipt == null && ticketId == null) return const SizedBox.shrink();

    final accepted = receipt?['accepted'] == true;
    final color = receipt == null
        ? AppTheme.accent2
        : accepted
            ? AppTheme.accent
            : AppTheme.danger;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Wrap(
        spacing: 16,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (receipt != null) ...[
            Icon(accepted ? Icons.check_circle : Icons.error_outline, size: 16, color: color),
            Text(
              accepted ? 'JOURNEY SUBMITTED' : 'SUBMISSION REFUSED',
              style: AppTheme.mono(10.5, color: color, tracking: 1.6, weight: FontWeight.w700),
            ),
            if (accepted)
              Text('REF ${receipt['reference']}',
                  style: AppTheme.mono(11.5, color: AppTheme.text, tracking: 0.8))
            else
              Flexible(
                child: Text('${receipt['error']}',
                    style: const TextStyle(fontSize: 12, color: AppTheme.text)),
              ),
            Text(
              'HTTP ${receipt['status_code']} - ${receipt['transport']} - ${receipt['latency_ms']}ms',
              style: const TextStyle(fontSize: 11, color: AppTheme.muted),
            ),
          ],
          if (ticketId != null) ...[
            const Icon(Icons.headset_mic, size: 16, color: AppTheme.warn),
            Text('HANDOFF $ticketId waiting in the Agent Inbox',
                style: const TextStyle(fontSize: 12, color: AppTheme.warn)),
            TextButton(
              onPressed: () => Navigator.of(context).pushNamed('/inbox'),
              child: const Text('Open inbox'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _timeline(List audit) {
    final items = audit.reversed.take(6).toList().reversed;
    return SizedBox(
      height: 72,
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        children: [
          Text('EVENT TIMELINE', style: _section()),
          const SizedBox(height: 4),
          Text(
            items.map((e) {
              final m = e as Map;
              final ts = '${m['timestamp'] ?? ''}'.split('T').last.split('.').first;
              return '$ts  ${m['event']}';
            }).join('   ·   '),
            style: const TextStyle(fontSize: 11, color: AppTheme.muted),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  /// DEMO CONTROLS - developer-only recovery panel.
  ///
  /// Every button sends a real, canonical customer utterance through the
  /// exact same `_send` path as typed or spoken input - nothing here bypasses
  /// the conversation manager, the guardrails, or the escalation engine. This
  /// exists purely so a presenter can recover instantly if the mic drops out
  /// or a live LLM call hiccups mid-demo, without breaking character by
  /// typing a full sentence. It is never shown to a customer and never wired
  /// into the production call path.
  Widget _demoControls() {
    if (!showDemoControls) return const SizedBox.shrink();

    Widget chip(String label, String utterance, {double conf = 0.95, Color? color}) {
      return OutlinedButton(
        onPressed: busy || callId == null ? null : () => _send(utterance, conf: conf),
        style: OutlinedButton.styleFrom(
          side: BorderSide(color: (color ?? AppTheme.lineSoft)),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        ),
        child: Text(
          label,
          style: AppTheme.mono(9.5, color: color ?? AppTheme.text, tracking: 0.8, weight: FontWeight.w700),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        border: Border.all(color: AppTheme.lineSoft, style: BorderStyle.solid),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.bolt, size: 14, color: AppTheme.accent),
              const SizedBox(width: 6),
              MonoLabel('DEMO CONTROLS - real utterances, one click', color: AppTheme.accent, size: 9),
              const Spacer(),
              MonoLabel('dev only', color: AppTheme.faint, size: 8.5),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              chip('CONSENT: YES', "Yes, that's fine"),
              chip('CONSENT: NO', "No, I don't consent to that"),
              chip('BUSY', "I'm actually at work right now"),
              chip('INTERRUPT', 'Wait, hold on'),
              chip('LOW CONFIDENCE', 'mumble not sure', conf: 0.3),
              chip('OFF-SCRIPT / ADVICE', 'Which plan should I choose, what do you recommend?'),
              chip('HUMAN REQUEST', 'Can I speak to a real person please', color: AppTheme.accent),
              chip('FRUSTRATION', "I've already told you this twice, this is ridiculous", color: AppTheme.accent),
              chip('PAYMENT MENTION', 'Can I just give you my card number now', color: AppTheme.accent),
              chip('NOT INTERESTED', "I'm not interested, thanks", color: AppTheme.accent),
            ],
          ),
        ],
      ),
    );
  }

  Widget _composer() {
    // On a real phone call, the customer's speech reaches the brain through
    // Twilio, not through this screen - there is nothing to type or speak
    // into here, so the composer becomes a live status line instead of an
    // input box that would silently do nothing.
    if (watchingRealCall) {
      final ended = turn['ended'] == true;
      return Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: AppTheme.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: ended ? AppTheme.lineSoft : AppTheme.accent),
          ),
          child: Row(
            children: [
              if (!ended) ...[
                const SizedBox(
                  width: 12, height: 12,
                  child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.accent),
                ),
                const SizedBox(width: 12),
                Text('Listening on the real phone call - the customer is speaking directly to Twilio',
                    style: AppTheme.prose(12.5).copyWith(color: AppTheme.text)),
              ] else
                Text('Call ended.', style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted)),
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Hold to talk (browser mic)',
            onPressed: () {
              if (voice.listening) {
                voice.stopListening();
              } else {
                voice.startListening();
              }
              setState(() {});
            },
            icon: Icon(voice.listening ? Icons.mic : Icons.mic_none, color: voice.listening ? AppTheme.danger : AppTheme.text),
          ),
          Expanded(
            child: TextField(
              controller: inputCtrl,
              onSubmitted: _send,
              decoration: InputDecoration(
                hintText: 'Customer says... (or use mic)',
                filled: true,
                fillColor: AppTheme.panel,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
              ),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: busy ? null : () => _send(inputCtrl.text),
            child: const Text('SEND'),
          ),
        ],
      ),
    );
  }

  Widget _panel({required Widget child}) {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppTheme.line),
      ),
      child: child,
    );
  }

  Widget _pill(String text, Color color) {
    final solid = color == AppTheme.accent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: solid ? AppTheme.accent : AppTheme.panelAlt,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        text.toUpperCase(),
        style: AppTheme.mono(9,
            color: solid ? AppTheme.bg : AppTheme.text, tracking: 1.2, weight: FontWeight.w700),
      ),
    );
  }

  TextStyle _section() => AppTheme.mono(10, color: AppTheme.label, tracking: 1.8);

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.only(bottom: 5),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 124, child: MonoLabel(k, size: 9)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(v, style: AppTheme.prose(12.5).copyWith(color: AppTheme.text)),
            ),
          ],
        ),
      );
}
