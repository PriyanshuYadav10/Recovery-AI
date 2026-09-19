import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';
import '../services/api_client.dart';

/// A two-column hero (pitch on the left, a live readout card on the right),
/// then three numbered sections down the page: run a scenario, work a real
/// lead sheet, and the guardrails that hold regardless.
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
  Widget build(BuildContext context) {
    final waiting = ((health['handoffs'] as Map?)?['waiting'] as num?)?.toInt() ?? 0;

    return Scaffold(
      backgroundColor: AppTheme.bg,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1080),
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(32, 28, 32, 40),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Masthead(
                    rightLabel: error == null ? 'LIVE  ·  ENERGY  ·  JAIPUR' : 'BACKEND OFFLINE',
                    online: error == null,
                  ),
                  const SizedBox(height: 44),

                  LayoutBuilder(builder: (context, c) {
                    final stacked = c.maxWidth < 760;
                    final left = FadeSlideIn(child: _heroPitch());
                    final right = FadeSlideIn(delay: const Duration(milliseconds: 90), child: _heroCard());
                    if (stacked) {
                      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        left,
                        const SizedBox(height: 28),
                        right,
                      ]);
                    }
                    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Expanded(flex: 6, child: left),
                      const SizedBox(width: 40),
                      SizedBox(width: 360, child: right),
                    ]);
                  }),

                  if (error != null) ...[
                    const SizedBox(height: 26),
                    Callout(
                      label: 'BACKEND OFFLINE',
                      child: Text(error!, style: AppTheme.prose(13)),
                    ),
                  ],

                  const SizedBox(height: 52),
                  const SectionLabel('01', 'Run it'),
                  const SizedBox(height: 16),
                  Text('Four scenarios, one click each', style: AppTheme.heading(26)),
                  const SizedBox(height: 6),
                  Text('Each one plays out the same journey under different pressure.',
                      style: AppTheme.prose(13).copyWith(color: AppTheme.muted)),
                  const SizedBox(height: 20),
                  Wrap(
                    spacing: 14,
                    runSpacing: 14,
                    children: [
                      _ScenarioCard(
                        icon: Icons.check_circle_outline,
                        title: 'SUCCESS',
                        body: 'A clean run - every field captured, journey submitted, no snags.',
                        onTap: () => _goConsole(scenario: 'success'),
                      ),
                      _ScenarioCard(
                        icon: Icons.graphic_eq,
                        title: 'MESSY CALL',
                        body: 'Hedges, interruptions and a corrected answer, handled without breaking script.',
                        onTap: () => _goConsole(scenario: 'messy'),
                      ),
                      _ScenarioCard(
                        icon: Icons.support_agent,
                        title: 'HANDOFF',
                        body: 'Frustration crosses the line - the agent hands off with a warm brief attached.',
                        onTap: () => _goConsole(scenario: 'handoff'),
                      ),
                      _ScenarioCard(
                        icon: Icons.block,
                        title: 'DNC BLOCK',
                        body: 'The number is on the Do-Not-Call list - the call is refused before it ever dials.',
                        onTap: () => _goConsole(scenario: 'dnc'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  Wrap(
                    spacing: 22,
                    runSpacing: 10,
                    children: [
                      _textLink(
                        waiting > 0 ? 'Agent Inbox  ·  $waiting waiting' : 'Agent Inbox',
                        () => Navigator.of(context).pushNamed('/inbox').then((_) => _load()),
                        emphasise: waiting > 0,
                      ),
                      _textLink('Evidence for the jury',
                          () => Navigator.of(context).pushNamed('/evidence')),
                    ],
                  ),

                  const SizedBox(height: 52),
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
                  HoverLift(
                    child: _cta('OPEN LEAD LIST', () => Navigator.of(context).pushNamed('/leads'),
                        primary: true),
                  ),

                  const SizedBox(height: 52),
                  const SectionLabel('02', 'Non-negotiable'),
                  const SizedBox(height: 16),
                  Text('Guardrails, designed in', style: AppTheme.heading(26)),
                  const SizedBox(height: 18),
                  Wrap(
                    spacing: 32,
                    runSpacing: 12,
                    children: const [
                      _GuardrailItem('Test data only'),
                      _GuardrailItem('Consent first'),
                      _GuardrailItem('No card data by voice'),
                      _GuardrailItem('No advice'),
                      _GuardrailItem('Do-Not-Call aware'),
                      _GuardrailItem('Respect "no"'),
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

  /// Left half of the hero: what this is, in one headline and one sentence.
  Widget _heroPitch() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
        const SizedBox(height: 26),
        HoverLift(
          child: _cta('START LIVE RECOVERY', () => _goConsole(leadId: 'EN-1001'), primary: true),
        ),
      ],
    );
  }

  /// Right half of the hero: the waveform and the numbers, as one raised
  /// card instead of loose elements on the page - this is the "device" the
  /// pitch is describing, so it earns its own surface.
  Widget _heroCard() {
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 20),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(16),
        boxShadow: AppTheme.cardShadow,
        border: Border.all(color: AppTheme.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const MonoLabel('ON THE LINE NOW'),
              const Spacer(),
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Waveform(levels: _waveLevels(metrics), height: 46),
          const HandoutRule(top: 22, bottom: 18),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              StatBlock('${metrics['journeys_started'] ?? 0}', 'Calls made', size: 26),
              StatBlock('${metrics['journeys_completed'] ?? 0}', 'Completed', size: 26),
              StatBlock('${metrics['human_handoffs'] ?? 0}', 'Handed off',
                  color: AppTheme.accent, size: 26),
            ],
          ),
        ],
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

  /// A quiet, secondary link - for things that matter but aren't a scenario
  /// to run (the inbox, the evidence page). Underlined weight only on hover.
  Widget _textLink(String label, VoidCallback onTap, {bool emphasise = false}) {
    final color = emphasise ? AppTheme.accent : AppTheme.body;
    return InkWell(
      onTap: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: AppTheme.prose(13.5).copyWith(color: color, fontWeight: FontWeight.w600)),
          const SizedBox(width: 4),
          Icon(Icons.arrow_forward, size: 14, color: color),
        ],
      ),
    );
  }

  /// One button shape used everywhere on this page: rounded, a tinted fill
  /// when it means something (primary action, or something waiting for
  /// attention), plain otherwise. The fix here matters, not just the look -
  /// the old version hard-coded white text on the orange fill, which fails
  /// contrast on a light background (3.08:1; ink on orange is 5.84:1).
  Widget _cta(String label, VoidCallback onTap, {bool primary = false, bool accent = false}) {
    final isAccent = primary || accent;
    return Material(
      color: primary ? AppTheme.accent : (accent ? AppTheme.accent.withValues(alpha: 0.08) : AppTheme.bg),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: primary ? null : Border.all(color: isAccent ? AppTheme.accent : AppTheme.lineSoft),
          ),
          child: Text(
            label,
            style: AppTheme.mono(10.5,
                color: primary ? AppTheme.ink : (accent ? AppTheme.accent : AppTheme.text),
                tracking: 1.2,
                weight: FontWeight.w700),
          ),
        ),
      ),
    );
  }
}

/// A scenario as a small card: what it's called, an icon, and one sentence
/// on what it actually demonstrates - the old version was seven identical
/// pills under a heading promising four scenarios, which didn't add up and
/// told you nothing about what you were about to click.
class _ScenarioCard extends StatelessWidget {
  const _ScenarioCard({required this.icon, required this.title, required this.body, required this.onTap});

  final IconData icon;
  final String title;
  final String body;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return HoverLift(
      lift: 4,
      borderRadius: 14,
      child: Material(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Container(
            width: 226,
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppTheme.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: Icon(icon, size: 18, color: AppTheme.accent),
                ),
                const SizedBox(height: 14),
                MonoLabel(title, color: AppTheme.text, size: 11.5),
                const SizedBox(height: 8),
                Text(body, style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted, height: 1.4)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One guardrail line: a check mark and the rule. Reads as a checklist
/// someone signed off on, not a bag of loose tags.
class _GuardrailItem extends StatelessWidget {
  const _GuardrailItem(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.check_circle, size: 16, color: AppTheme.accent),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: AppTheme.prose(13.5).copyWith(color: AppTheme.text))),
        ],
      ),
    );
  }
}
