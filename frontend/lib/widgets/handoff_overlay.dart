import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';

Future<void> showHandoffOverlay(
  BuildContext context,
  Map<String, dynamic> brief,
  Map<String, dynamic> snapshot,
) async {
  final phases = [
    'FRUSTRATION DETECTED',
    'HUMAN REQUEST',
    'HANDOFF PREPARING',
    'CONTEXT PACKAGED',
    'HUMAN READY',
  ];

  await showGeneralDialog(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'handoff',
    barrierColor: Colors.black87,
    pageBuilder: (ctx, a1, a2) {
      return _HandoffDialog(brief: brief, phases: phases);
    },
  );
}

class _HandoffDialog extends StatefulWidget {
  const _HandoffDialog({required this.brief, required this.phases});
  final Map<String, dynamic> brief;
  final List<String> phases;

  @override
  State<_HandoffDialog> createState() => _HandoffDialogState();
}

class _HandoffDialogState extends State<_HandoffDialog> {
  int phaseIdx = 0;

  @override
  void initState() {
    super.initState();
    _animate();
  }

  Future<void> _animate() async {
    for (var i = 0; i < widget.phases.length; i++) {
      await Future.delayed(const Duration(milliseconds: 450));
      if (!mounted) return;
      setState(() => phaseIdx = i);
    }
  }

  @override
  Widget build(BuildContext context) {
    final b = widget.brief;
    final fields = (b['fields_collected'] as List?) ?? [];
    return Center(
      child: Material(
        color: Colors.transparent,
        child: Container(
          width: 720,
          constraints: const BoxConstraints(maxHeight: 640),
          margin: const EdgeInsets.all(24),
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFF121A2B),
            borderRadius: BorderRadius.circular(18),
            border: const Border(left: BorderSide(color: AppTheme.accent, width: 4)),
            boxShadow: const [
              BoxShadow(color: Color(0x66000000), blurRadius: 40),
            ],
          ),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // The handout marks the turn with an arrow and sets it in
                // the accent: "FRUSTRATION DETECTED - WARM HANDOFF".
                Row(
                  children: [
                    Text('\u21B3', style: AppTheme.heading(20).copyWith(color: AppTheme.accent)),
                    const SizedBox(width: 8),
                    Text('FRUSTRATION DETECTED - WARM HANDOFF',
                        style: AppTheme.mono(13, color: AppTheme.accent,
                            tracking: 1.4, weight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (var i = 0; i <= phaseIdx && i < widget.phases.length; i++)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                        decoration: BoxDecoration(
                          color: i == phaseIdx ? AppTheme.accent : AppTheme.panelAlt,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(widget.phases[i],
                            style: AppTheme.mono(9,
                                color: i == phaseIdx ? AppTheme.bg : AppTheme.text,
                                tracking: 1.2,
                                weight: FontWeight.w700)),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  "Don't make the customer repeat themselves.",
                  style: AppTheme.prose(15).copyWith(fontStyle: FontStyle.italic, color: AppTheme.text),
                ),
                const SizedBox(height: 18),
                Text('LIVE HANDOFF BRIEF', style: AppTheme.heading(16)),
                const Divider(color: AppTheme.line, height: 22),
                _line('Customer', '${b['customer']}'),
                _line('Journey', '${b['journey']}'),
                _line('Current stage', '${b['current_stage']}'),
                _line('Reason', '${b['reason']}'),
                _line('Confidence', '${((b['confidence'] ?? 0.9) as num) * 100}%'),
                _line('Customer mood', '${b['customer_mood']}'),
                const SizedBox(height: 8),
                const MonoLabel('FIELDS ALREADY COLLECTED'),
                const SizedBox(height: 6),
                ...fields.map((f) => Text('· $f', style: AppTheme.prose(13).copyWith(color: AppTheme.accent))),
                const SizedBox(height: 8),
                _line('Last customer statement', '"${b['last_customer_statement']}"'),
                _line('Recommended human opening', '${b['recommended_opening']}'),
                _line('Conversation summary', '${b['conversation_summary']}'),
                _line('Next action', '${b['next_action']}'),
                const SizedBox(height: 16),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('CLOSE BRIEF'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _line(String k, String v) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: RichText(
          text: TextSpan(children: [
            TextSpan(text: '$k:\n', style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
            TextSpan(text: v, style: const TextStyle(height: 1.35)),
          ]),
        ),
      );
}
