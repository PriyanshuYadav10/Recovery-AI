import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';
import '../services/api_client.dart';

/// Laid out as a page of the CIMET handout: masthead, display heading with the
/// accent word, waveform, stat row, then numbered sections down the page.
class LandingScreen extends StatefulWidget {
  const LandingScreen({super.key});

  @override
  State<LandingScreen> createState() => _LandingScreenState();
}

class _LandingScreenState extends State<LandingScreen> {
  final api = ApiClient();
  Map<String, dynamic> metrics = {};
  Map<String, dynamic> health = {};
  Map<String, dynamic> queue = {};
  String? error;

  final phoneCtrl = TextEditingController();
  String dialLeadId = 'EN-1001';
  bool dialing = false;
  String? dialStatus;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final h = await api.health();
      final m = await api.metrics();
      final q = await api.prioritisedLeads();
      if (!mounted) return;
      setState(() {
        health = h;
        metrics = m;
        queue = q;
        error = null;
      });
    } catch (_) {
      if (mounted) setState(() => error = 'Backend offline - start the API on :8000');
    }
  }

  Future<void> _dialReal() async {
    final phone = phoneCtrl.text.trim();
    if (phone.isEmpty) {
      setState(() => dialStatus = 'Enter a real, verified number first.');
      return;
    }
    setState(() {
      dialing = true;
      dialStatus = 'Dialling $phone ...';
    });
    try {
      final res = await api.dialReal(leadId: dialLeadId, phone: phone);
      if (res['dialled'] == false) {
        setState(() => dialStatus =
            'Blocked before dialling: ${res['blocked_by']} - ${res['detail']?['reason'] ?? 'not eligible'}');
        return;
      }
      final dialResult = (res['dial_result'] as Map?) ?? {};
      final status = dialResult['status'];
      if (status == 'bridge_unavailable' || status == 'dial_failed') {
        setState(() => dialStatus =
            'Twilio bridge did not accept the call: ${dialResult['error'] ?? status}. '
            'Is telephony/bridge running (npm start) and .env filled in?');
        return;
      }
      final callId = res['call_id'] as String?;
      if (callId == null) {
        setState(() => dialStatus = 'No call_id returned - unexpected response.');
        return;
      }
      setState(() => dialStatus = 'Ringing. Opening the live console...');
      if (!mounted) return;
      await Navigator.of(context)
          .pushNamed('/console', arguments: {'callId': callId, 'watch': true});
      if (mounted) setState(() => dialStatus = null);
    } catch (e) {
      setState(() => dialStatus = 'Dial failed: $e');
    } finally {
      if (mounted) setState(() => dialing = false);
    }
  }

  void _goConsole({String? scenario, String? leadId}) {
    Navigator.of(context).pushNamed('/console', arguments: {
      if (scenario != null) 'scenario': scenario,
      if (leadId != null) 'leadId': leadId,
      'autoStart': true,
    }).then((_) => _load());
  }

  @override
  void dispose() {
    phoneCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final groq = (health['groq'] as Map?) ?? {};
    final vsManual = (metrics['vs_manual'] as Map?)?.cast<String, dynamic>() ?? {};
    final waiting = ((health['handoffs'] as Map?)?['waiting'] as num?)?.toInt() ?? 0;

    return Scaffold(
      backgroundColor: AppTheme.bg,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 940),
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(32, 28, 32, 40),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Masthead(
                    rightLabel: error == null ? 'LIVE  ·  ENERGY  ·  JAIPUR' : 'BACKEND OFFLINE',
                    online: error == null,
                  ),
                  const SizedBox(height: 46),

                  const SectionLabel('00', 'Dropout recovery'),
                  const SizedBox(height: 18),
                  const DisplayHeading('Recover the\njourney. ', accentWord: 'Listen.'),
                  const SizedBox(height: 18),
                  SizedBox(
                    width: 460,
                    child: Text(
                      'An AI voice agent that finishes a dropped Energy comparison over '
                      'a real phone call - and hands a frustrated caller back to a human, '
                      'with everything collected so far.',
                      style: AppTheme.prose(15),
                    ),
                  ),
                  const SizedBox(height: 30),
                  Waveform(levels: _waveLevels(metrics)),
                  const HandoutRule(top: 26, bottom: 22),

                  Wrap(
                    spacing: 56,
                    runSpacing: 18,
                    children: [
                      StatBlock('${metrics['journeys_started'] ?? 0}', 'RECOVERIES RUN'),
                      StatBlock('${metrics['journeys_completed'] ?? 0}', 'COMPLETED'),
                      StatBlock('${metrics['human_handoffs'] ?? 0}', 'HANDOFFS',
                          color: AppTheme.accent),
                      StatBlock(
                        '${(((metrics['automation_rate'] ?? 0) as num) * 100).round()}%',
                        'FIELDS AUTOMATED',
                      ),
                      StatBlock(
                        groq['connected'] == true ? 'Groq' : 'Rules',
                        'REASONING MODE',
                        size: 22,
                      ),
                    ],
                  ),

                  if (error != null) ...[
                    const SizedBox(height: 26),
                    Callout(
                      label: 'BACKEND OFFLINE',
                      child: Text(error!, style: AppTheme.prose(13)),
                    ),
                  ],

                  const SizedBox(height: 46),
                  const SectionLabel('01', 'Run it'),
                  const SizedBox(height: 16),
                  Text('Four scenarios, one click each', style: AppTheme.heading(26)),
                  const SizedBox(height: 18),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      _cta('START LIVE RECOVERY', () => _goConsole(leadId: 'EN-1001'),
                          primary: true),
                      _cta('SUCCESS SCENARIO', () => _goConsole(scenario: 'success')),
                      _cta('MESSY CALL', () => _goConsole(scenario: 'messy')),
                      _cta('HANDOFF SCENARIO', () => _goConsole(scenario: 'handoff')),
                      _cta('DNC BLOCK', () => _goConsole(scenario: 'dnc')),
                      _cta(
                        waiting > 0 ? 'AGENT INBOX ($waiting)' : 'AGENT INBOX',
                        () => Navigator.of(context).pushNamed('/inbox').then((_) => _load()),
                        accent: waiting > 0,
                      ),
                    ],
                  ),

                  const SizedBox(height: 46),
                  const SectionLabel('01B', 'Real phone call'),
                  const SizedBox(height: 16),
                  Text('Dial a real number, live', style: AppTheme.heading(26)),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: 520,
                    child: Text(
                      'Everything above runs in browser simulation. This actually rings a '
                      'phone through Twilio - enter a verified test number you control, using '
                      'a synthetic lead\'s journey context for what it already knows.',
                      style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
                    ),
                  ),
                  const SizedBox(height: 16),
                  HandoutPanel(
                    label: 'OUTBOUND CALL - TWILIO BRIDGE',
                    trailing: MonoLabel(
                      health['telephony_bridge'] != null ? 'BRIDGE CONFIGURED' : 'BRIDGE UNKNOWN',
                      color: AppTheme.faint,
                      size: 9,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            SizedBox(
                              width: 240,
                              child: TextField(
                                controller: phoneCtrl,
                                enabled: !dialing,
                                style: AppTheme.prose(13),
                                decoration: const InputDecoration(
                                  hintText: '+91XXXXXXXXXX (verified number)',
                                  isDense: true,
                                ),
                              ),
                            ),
                            SizedBox(
                              width: 160,
                              child: DropdownButtonFormField<String>(
                                initialValue: dialLeadId,
                                isDense: true,
                                decoration: const InputDecoration(isDense: true),
                                dropdownColor: AppTheme.panel,
                                style: AppTheme.prose(13).copyWith(color: AppTheme.text),
                                items: const [
                                  DropdownMenuItem(value: 'EN-1001', child: Text('EN-1001')),
                                  DropdownMenuItem(value: 'EN-1002', child: Text('EN-1002')),
                                  DropdownMenuItem(value: 'EN-1003', child: Text('EN-1003')),
                                ],
                                onChanged: dialing
                                    ? null
                                    : (v) => setState(() => dialLeadId = v ?? dialLeadId),
                              ),
                            ),
                            FilledButton.icon(
                              onPressed: dialing ? null : _dialReal,
                              icon: dialing
                                  ? const SizedBox(
                                      width: 14, height: 14,
                                      child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.bg),
                                    )
                                  : const Icon(Icons.call, size: 16),
                              label: Text(dialing ? 'DIALLING' : 'CALL'),
                            ),
                          ],
                        ),
                        if (dialStatus != null) ...[
                          const SizedBox(height: 10),
                          Text(dialStatus!,
                              style: AppTheme.prose(12.5).copyWith(color: AppTheme.accent)),
                        ],
                        const SizedBox(height: 10),
                        Text(
                          'Trial Twilio accounts can only call numbers verified in the Twilio '
                          'console. DNC is checked before the dial - a listed lead never rings.',
                          style: AppTheme.prose(11).copyWith(color: AppTheme.faint),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 46),
                  const SectionLabel('02', 'How the call runs'),
                  const SizedBox(height: 16),
                  Text('Gate, disclose, resume, submit', style: AppTheme.heading(26)),
                  const SizedBox(height: 22),
                  const Wrap(
                    spacing: 28,
                    runSpacing: 22,
                    children: [
                      NumberedCard(
                        number: '01',
                        title: 'DNC gates the dial',
                        body: 'The register is checked before the phone rings, not after.',
                      ),
                      NumberedCard(
                        number: '02',
                        title: 'Consent first',
                        body: 'Recording is disclosed before a single field is collected.',
                      ),
                      NumberedCard(
                        number: '03',
                        title: 'Resume, do not restart',
                        body: 'Only the missing Energy fields are asked for.',
                      ),
                      NumberedCard(
                        number: '04',
                        title: 'Submit and confirm',
                        body: 'The payload is posted and the reference read back aloud.',
                      ),
                    ],
                  ),

                  if (queue['queue'] != null) ...[
                    const SizedBox(height: 46),
                    const SectionLabel('03', 'Who gets called first'),
                    const SizedBox(height: 16),
                    Text('The queue is ranked, not arbitrary', style: AppTheme.heading(26)),
                    const SizedBox(height: 18),
                    _callQueue(queue),
                  ],

                  if (vsManual.isNotEmpty) ...[
                    const SizedBox(height: 46),
                    const SectionLabel('04', 'Versus today'),
                    const SizedBox(height: 16),
                    Text('Measured against the manual workflow', style: AppTheme.heading(26)),
                    const SizedBox(height: 18),
                    _comparison(vsManual),
                  ],

                  const SizedBox(height: 46),
                  const SectionLabel('05', 'Non-negotiable'),
                  const SizedBox(height: 16),
                  Text('Guardrails, designed in', style: AppTheme.heading(26)),
                  const SizedBox(height: 18),
                  const Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      HandoutChip('Test data only'),
                      HandoutChip('Consent first'),
                      HandoutChip('No card data by voice'),
                      HandoutChip('No advice'),
                      HandoutChip('Do-Not-Call aware'),
                      HandoutChip('Respect "no"'),
                    ],
                  ),
                  const SizedBox(height: 22),
                  Callout(
                    label: 'READ THE ROOM',
                    child: Text(
                      'Know when to step aside. Then recover the journey.',
                      style: AppTheme.prose(14).copyWith(color: AppTheme.text),
                    ),
                  ),

                  const HandoutFooter(
                    left: 'CIMET · ECONNEX - RECOVERY AI',
                    right: 'ENERGY · TEST DATA ONLY',
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// The cover waveform, shaped by whatever the system has actually done.
  List<double> _waveLevels(Map<String, dynamic> m) {
    final seedValues = [
      (m['journeys_started'] ?? 3) as num,
      (m['journeys_completed'] ?? 2) as num,
      (m['human_handoffs'] ?? 1) as num,
      (m['clarifications'] ?? 1) as num,
      (m['interruptions'] ?? 1) as num,
    ];
    final base = <double>[
      0.45, 0.72, 0.38, 0.9, 0.55, 0.68, 0.32, 0.82, 0.5, 0.95, 0.42, 0.6,
      0.78, 0.35, 0.88, 0.52, 0.7, 0.4, 0.92, 0.48, 0.65, 0.3, 0.85, 0.58,
    ];
    return [
      for (var i = 0; i < base.length; i++)
        (base[i] * (1 + (seedValues[i % seedValues.length] % 3) * 0.06)).clamp(0.12, 1.0),
    ];
  }

  Widget _cta(String label, VoidCallback onTap, {bool primary = false, bool accent = false}) {
    final isAccent = primary || accent;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
        decoration: BoxDecoration(
          color: primary ? AppTheme.accent : Colors.transparent,
          border: Border.all(color: isAccent ? AppTheme.accent : AppTheme.lineSoft),
        ),
        child: Text(
          label,
          style: AppTheme.mono(10.5,
              color: primary
                  ? AppTheme.bg
                  : (accent ? AppTheme.accent : AppTheme.text),
              tracking: 1.4,
              weight: FontWeight.w700),
        ),
      ),
    );
  }

  Widget _callQueue(Map<String, dynamic> q) {
    final rows = ((q['queue'] as List?) ?? []).cast<Map<String, dynamic>>();
    final blocked = ((q['blocked_by_dnc'] as List?) ?? []).cast<Map<String, dynamic>>();

    return HandoutPanel(
      label: 'CALL QUEUE · RANKED BY RECOVERY PROPENSITY',
      trailing: MonoLabel('${q['scored_by']} ${q['model_version'] ?? ''}',
          color: AppTheme.faint, size: 9),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...rows.take(6).map((r) {
            final band = '${r['band']}';
            final colour = AppTheme.band(band);
            final pct = (((r['recovery_probability'] as num?) ?? 0) * 100).round();
            final reasons = ((r['reasons'] as List?) ?? []).cast<String>();
            return Padding(
              padding: const EdgeInsets.only(bottom: 11),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 30,
                    child: Text('${r['queue_position']}'.padLeft(2, '0'),
                        style: AppTheme.mono(11, color: AppTheme.numeral, tracking: 0.5)),
                  ),
                  SizedBox(
                    width: 140,
                    child: Text('${r['customer']}', style: AppTheme.prose(13).copyWith(color: AppTheme.text)),
                  ),
                  SizedBox(width: 62, child: Text('$pct%', style: AppTheme.figure(15, color: colour))),
                  SizedBox(width: 78, child: MonoLabel(band, color: colour, size: 9)),
                  Expanded(
                    child: Text(
                      reasons.isEmpty ? '' : reasons.first,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTheme.prose(12).copyWith(color: AppTheme.muted),
                    ),
                  ),
                ],
              ),
            );
          }),
          if (blocked.isNotEmpty) ...[
            const HandoutRule(top: 8, bottom: 12),
            Row(
              children: [
                const MonoLabel('REMOVED BEFORE RANKING · DNC', color: AppTheme.accent, size: 9),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    blocked.map((b) => b['customer']).join(', '),
                    style: AppTheme.prose(12).copyWith(color: AppTheme.muted),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _comparison(Map<String, dynamic> v) {
    String secs(dynamic n) {
      final d = (n as num?)?.toDouble() ?? 0;
      if (d <= 0) return '-';
      final m = d ~/ 60;
      final rem = (d % 60).round();
      return m > 0 ? '${m}m ${rem}s' : '${rem}s';
    }

    final reduction = (((v['handle_time_reduction'] as num?) ?? 0) * 100).round();
    final measured = (v['calls_measured'] as num?)?.toInt() ?? 0;

    return HandoutPanel(
      label: 'EFFICIENCY GAIN',
      trailing: MonoLabel(
        measured == 0 ? 'NO COMPLETED CALLS YET' : '$measured CALL(S) MEASURED',
        color: AppTheme.faint,
        size: 9,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (measured == 0)
            // Nothing has been measured yet, so show the manual baseline alone
            // rather than a saving of zero, which would read as "no gain".
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Manual baseline today: ${secs(v['manual_handle_time_sec'])} per call, '
                  '${v['manual_fields_typed'] ?? 0} fields typed by an agent, '
                  '${v['manual_script_lookups'] ?? 0} script lookups.',
                  style: AppTheme.prose(13),
                ),
                const SizedBox(height: 8),
                Text('Run a recovery and the comparison fills in here.',
                    style: AppTheme.prose(12).copyWith(color: AppTheme.muted)),
              ],
            )
          else
            Wrap(
              spacing: 34,
              runSpacing: 18,
              children: [
                _delta('HANDLE TIME', secs(v['manual_handle_time_sec']),
                    secs(v['ai_handle_time_sec']), '$reduction% faster'),
                _delta('FIELDS TYPED BY AN AGENT', '${v['manual_fields_typed'] ?? 0}',
                    '${v['ai_fields_typed'] ?? 0}', 'captured by voice'),
                _delta('SCRIPT LOOKUPS', '${v['manual_script_lookups'] ?? 0}',
                    '${v['ai_script_lookups'] ?? 0}', 'scripts drive the call'),
                _delta('JOURNEYS / AGENT HOUR', '${v['manual_journeys_per_agent_hour'] ?? 0}',
                    '${v['ai_journeys_per_agent_hour'] ?? 0}', '${v['throughput_multiple'] ?? 0}x'),
              ],
            ),
          const SizedBox(height: 16),
          Text('${v['note'] ?? ''}',
              style: AppTheme.prose(11).copyWith(color: AppTheme.faint, height: 1.5)),
        ],
      ),
    );
  }

  Widget _delta(String label, String manual, String ai, String caption) {
    return SizedBox(
      width: 200,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          MonoLabel(label, size: 9),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(manual,
                  style: AppTheme.prose(14).copyWith(
                      color: AppTheme.faint, decoration: TextDecoration.lineThrough)),
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward, size: 12, color: AppTheme.faint),
              const SizedBox(width: 8),
              Text(ai, style: AppTheme.figure(19, color: AppTheme.accent)),
            ],
          ),
          const SizedBox(height: 4),
          Text(caption, style: AppTheme.prose(11).copyWith(color: AppTheme.muted)),
        ],
      ),
    );
  }
}
