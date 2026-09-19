import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';
import '../services/api_client.dart';

/// Agent Inbox - where a warm handoff actually lands.
///
/// Set as a page of the handout: mono section labels, square ruled panels, the
/// transcript typeset with inline speaker tags rather than chat bubbles.
class InboxScreen extends StatefulWidget {
  const InboxScreen({super.key});

  @override
  State<InboxScreen> createState() => _InboxScreenState();
}

class _InboxScreenState extends State<InboxScreen> {
  final api = ApiClient();
  final replyCtrl = TextEditingController();

  List<Map<String, dynamic>> tickets = [];
  Map<String, dynamic> stats = {};
  Map<String, dynamic>? selected;
  Timer? poll;
  String? error;
  bool busy = false;
  String agentName = 'Aarav';

  @override
  void initState() {
    super.initState();
    _load();
    poll = Timer.periodic(const Duration(seconds: 3), (_) => _load(quiet: true));
  }

  @override
  void dispose() {
    poll?.cancel();
    replyCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({bool quiet = false}) async {
    try {
      final res = await api.handoffs();
      if (!mounted) return;
      setState(() {
        stats = (res['stats'] as Map?)?.cast<String, dynamic>() ?? {};
        tickets = ((res['tickets'] as List?) ?? [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
        if (selected != null) {
          final id = selected!['ticket_id'];
          selected = tickets.firstWhere((t) => t['ticket_id'] == id, orElse: () => selected!);
        }
        error = null;
      });
    } catch (_) {
      if (!quiet && mounted) setState(() => error = 'Backend offline - start the API on :8000');
    }
  }

  Future<void> _act(Future<Map<String, dynamic>> Function() action) async {
    setState(() => busy = true);
    try {
      final updated = await action();
      setState(() => selected = updated);
      await _load(quiet: true);
    } catch (e) {
      setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Color _statusColour(String status) => switch (status) {
        'WAITING' => AppTheme.accent,
        'CLAIMED' => AppTheme.text,
        _ => AppTheme.faint,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bg,
      body: SafeArea(
        child: Column(
          children: [
            _header(),
            if (error != null)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
                decoration: const BoxDecoration(
                  border: Border(left: BorderSide(color: AppTheme.accent, width: 3)),
                  color: AppTheme.panel,
                ),
                child: Text(error!, style: AppTheme.prose(12.5).copyWith(color: AppTheme.accent)),
              ),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(width: 330, child: _queue()),
                  Container(width: 1, color: AppTheme.line),
                  Expanded(child: selected == null ? _empty() : _detail(selected!)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header() {
    final waiting = '${stats['waiting'] ?? 0}';
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 14),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.line)),
      ),
      child: Row(
        children: [
          Text('CIMET.', style: AppTheme.heading(15)),
          const SizedBox(width: 6),
          Text('/ agent inbox', style: AppTheme.prose(13).copyWith(color: AppTheme.muted)),
          const SizedBox(width: 26),
          _stat(waiting, 'WAITING', accent: (stats['waiting'] ?? 0) != 0),
          const SizedBox(width: 22),
          _stat('${stats['claimed'] ?? 0}', 'CLAIMED'),
          const SizedBox(width: 22),
          _stat('${stats['average_wait_sec'] ?? 0}s', 'AVG WAIT'),
          const Spacer(),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const MonoLabel('BACK', color: AppTheme.accent, size: 9.5),
          ),
        ],
      ),
    );
  }

  Widget _stat(String value, String label, {bool accent = false}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text(value,
            style: AppTheme.figure(17, color: accent ? AppTheme.accent : AppTheme.ink)),
        const SizedBox(width: 8),
        MonoLabel(label, size: 9),
      ],
    );
  }

  Widget _empty() => Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Text(
            tickets.isEmpty
                ? 'No handoffs yet. Run the handoff scenario and it lands here.'
                : 'Select a handoff to see the context.',
            style: AppTheme.prose(13).copyWith(color: AppTheme.faint),
          ),
        ),
      );

  Widget _queue() {
    if (tickets.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: MonoLabel('QUEUE EMPTY', color: AppTheme.faint, size: 9.5),
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: tickets.length,
      itemBuilder: (_, i) {
        final t = tickets[i];
        final status = '${t['status']}';
        final colour = _statusColour(status);
        final isSelected = selected?['ticket_id'] == t['ticket_id'];
        return InkWell(
          onTap: () => setState(() => selected = t),
          child: Container(
            padding: const EdgeInsets.fromLTRB(20, 14, 16, 14),
            decoration: BoxDecoration(
              color: isSelected ? AppTheme.panel : Colors.transparent,
              border: Border(
                left: BorderSide(
                  color: isSelected ? AppTheme.accent : Colors.transparent,
                  width: 3,
                ),
                bottom: const BorderSide(color: AppTheme.line),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text('${t['customer']}',
                          style: AppTheme.prose(14).copyWith(
                              color: AppTheme.text, fontWeight: FontWeight.w600)),
                    ),
                    MonoLabel('${t['ticket_id']}', color: AppTheme.numeral, size: 9),
                  ],
                ),
                const SizedBox(height: 6),
                Text('${t['reason']}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppTheme.prose(12).copyWith(color: AppTheme.muted)),
                const SizedBox(height: 8),
                Row(
                  children: [
                    MonoLabel(status, color: colour, size: 9),
                    const SizedBox(width: 10),
                    MonoLabel('VIA ${t['voice_mode'] ?? '-'}', color: AppTheme.faint, size: 9),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _detail(Map<String, dynamic> t) {
    final brief = (t['brief'] as Map?)?.cast<String, dynamic>() ?? {};
    final fields = (t['fields'] as Map?)?.cast<String, dynamic>() ?? {};
    final transcript = ((t['transcript'] as List?) ?? [])
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
    final claimed = t['status'] != 'WAITING';
    final resolved = t['status'] == 'RESOLVED';

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel('${t['ticket_id']}'.replaceAll('HO-', ''), 'Warm handoff'),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: Text('${t['customer']}', style: AppTheme.heading(28))),
              if (!claimed)
                FilledButton(
                  onPressed: busy
                      ? null
                      : () => _act(() => api.claimHandoff(t['ticket_id'] as String, agentName)),
                  child: Text('CLAIM AS ${agentName.toUpperCase()}'),
                )
              else if (!resolved)
                OutlinedButton(
                  onPressed: busy
                      ? null
                      : () => _act(() => api.resolveHandoff(
                          t['ticket_id'] as String, 'Handled by $agentName')),
                  child: const Text('RESOLVE'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('↳', style: AppTheme.heading(16).copyWith(color: AppTheme.accent)),
              const SizedBox(width: 8),
              Expanded(
                child: Text('${t['reason']}'.toUpperCase(),
                    style: AppTheme.mono(11, color: AppTheme.accent,
                        tracking: 1.2, weight: FontWeight.w700)),
              ),
            ],
          ),
          if (t['claimed_by'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Claimed by ${t['claimed_by']} after ${t['wait_seconds']}s waiting',
                style: AppTheme.prose(12).copyWith(color: AppTheme.muted),
              ),
            ),
          const SizedBox(height: 22),

          HandoutPanel(
            label: 'HANDOFF BRIEF',
            trailing: MonoLabel(
                ((t['signals'] as List?) ?? []).join(' · '),
                color: AppTheme.faint, size: 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (brief['recommended_opening'] != null) ...[
                  Text('"${brief['recommended_opening']}"',
                      style: AppTheme.prose(14).copyWith(
                          color: AppTheme.text, fontStyle: FontStyle.italic)),
                  const SizedBox(height: 14),
                ],
                _kv('SO FAR', '${brief['conversation_summary'] ?? '-'}'),
                _kv('NEXT', '${brief['next_action'] ?? '-'}'),
                _kv('STAGE', '${brief['current_stage'] ?? '-'}'),
                _kv('MOOD', '${brief['customer_mood'] ?? '-'}'),
              ],
            ),
          ),
          const SizedBox(height: 16),

          HandoutPanel(
            label: 'ALREADY COLLECTED · DO NOT ASK AGAIN',
            child: fields.isEmpty
                ? Text('Nothing captured yet',
                    style: AppTheme.prose(12.5).copyWith(color: AppTheme.faint))
                : Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      for (final e in fields.entries)
                        HandoutChip('${e.key.replaceAll('_', ' ')}: ${e.value}', active: true),
                    ],
                  ),
          ),
          const SizedBox(height: 16),

          HandoutPanel(
            label: 'CONVERSATION',
            trailing: MonoLabel('${transcript.length} TURNS', color: AppTheme.faint, size: 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final m in transcript) _transcriptLine(m),
              ],
            ),
          ),

          if (claimed && !resolved) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: replyCtrl,
                    style: AppTheme.prose(13),
                    onSubmitted: (_) => _sendReply(t),
                    decoration: const InputDecoration(
                      hintText: 'Continue as the human agent...',
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                FilledButton(
                  onPressed: busy ? null : () => _sendReply(t),
                  child: const Text('SEND'),
                ),
              ],
            ),
          ],
          if (resolved)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: MonoLabel('RESOLVED · ${t['resolution']}',
                  color: AppTheme.muted, size: 9.5),
            ),
          const HandoutFooter(left: 'CIMET · ECONNEX - AGENT INBOX', right: 'WARM HANDOFF'),
        ],
      ),
    );
  }

  void _sendReply(Map<String, dynamic> t) {
    final text = replyCtrl.text.trim();
    if (text.isEmpty) return;
    replyCtrl.clear();
    _act(() => api.handoffMessage(t['ticket_id'] as String, text));
  }

  Widget _transcriptLine(Map<String, dynamic> m) {
    final role = '${m['role']}';
    final tag = switch (role) {
      'assistant' => 'AI AGENT',
      'human_agent' => 'HUMAN',
      _ => 'CUSTOMER',
    };
    final colour = switch (role) {
      'assistant' => AppTheme.accent,
      'human_agent' => AppTheme.text,
      _ => AppTheme.muted,
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          MonoLabel(tag, color: colour, size: 9),
          const SizedBox(height: 4),
          Text('${m['text']}', style: AppTheme.prose(13)),
        ],
      ),
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 78, child: MonoLabel(k, size: 9)),
            Expanded(child: Text(v, style: AppTheme.prose(13))),
          ],
        ),
      );
}
