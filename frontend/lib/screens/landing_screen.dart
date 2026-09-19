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
  String? error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final h = await api.health();
      final m = await api.metrics();
      if (!mounted) return;
      setState(() {
        health = h;
        metrics = m;
        error = null;
      });
    } catch (_) {
      if (mounted) setState(() => error = 'Backend offline - start the API on :8000');
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


  @override
  Widget build(BuildContext context) {
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
                      StatBlock('${metrics['journeys_started'] ?? 0}', 'Calls made'),
                      StatBlock('${metrics['journeys_completed'] ?? 0}', 'Completed'),
                      StatBlock('${metrics['human_handoffs'] ?? 0}', 'Handed to a person',
                          color: AppTheme.accent),
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
                      _cta('EVIDENCE', () => Navigator.of(context).pushNamed('/evidence')),
                    ],
                  ),

                  const SizedBox(height: 46),
                  const SectionLabel('01A', 'Work a lead sheet'),
                  const SizedBox(height: 16),
                  Text('Upload a sheet, call down the list', style: AppTheme.heading(26)),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: 520,
                    child: Text(
                      'This is the one place to make a real call. Upload a CSV or Excel '
                      'sheet of leads, call any one of them straight from the list with a '
                      'number you have confirmed with your provider, watch the transcript '
                      'live, and every outcome is saved back onto that row.',
                      style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
                    ),
                  ),
                  const SizedBox(height: 16),
                  _cta('OPEN LEAD LIST', () => Navigator.of(context).pushNamed('/leads'),
                      primary: true),

                  const SizedBox(height: 46),
                  const SectionLabel('02', 'Non-negotiable'),
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

}
