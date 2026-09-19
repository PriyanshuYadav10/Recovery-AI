import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/api_client.dart';

/// A scripted or typed-in-browser demo call: who it is, what's been said,
/// how it ended. No scores, no internal event log, no jargon panels.
///
/// Real phone calls are watched from the lead list (/leads) instead, which
/// has its own inline transcript - this screen only ever drives the four
/// demo-button scenarios and the browser-typed "start live recovery" path.
class ConsoleScreen extends StatefulWidget {
  const ConsoleScreen({super.key});

  @override
  State<ConsoleScreen> createState() => _ConsoleScreenState();
}

class _ConsoleScreenState extends State<ConsoleScreen> {
  final api = ApiClient();
  final inputCtrl = TextEditingController();
  final scrollCtrl = ScrollController();

  String? callId;
  Map<String, dynamic> snapshot = {};
  Map<String, dynamic> turn = {};
  List<Map<String, dynamic>> transcript = [];
  List<String> demoQueue = [];
  bool busy = false;
  bool live = false;
  String? banner;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    inputCtrl.dispose();
    scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final args = ModalRoute.of(context)?.settings.arguments as Map?;
    if (args == null) return;
    final scenario = args['scenario'] as String?;
    final leadId = args['leadId'] as String? ?? 'EN-1001';
    if (args['autoStart'] == true) {
      await _start(leadId: leadId, scenario: scenario);
    }
  }

  Future<void> _start({required String leadId, String? scenario}) async {
    setState(() {
      busy = true;
      banner = null;
      transcript = [];
    });
    try {
      final res = await api.startCall(leadId: leadId, voiceMode: 'BROWSER', scenario: scenario);
      callId = res['call_id'] as String;
      turn = (res['turn'] as Map).cast<String, dynamic>();
      snapshot = (res['snapshot'] as Map).cast<String, dynamic>();
      _ingestTranscript(snapshot);
      final utts = res['scenario_utterances'];
      demoQueue = utts is List ? utts.map((e) => '$e').toList() : <String>[];
      live = true;
      if (scenario != null && demoQueue.isNotEmpty) unawaited(_autoDemo());
    } catch (e) {
      setState(() => banner = 'Could not start the call - $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _autoDemo() async {
    while (demoQueue.isNotEmpty && mounted && live) {
      await Future.delayed(const Duration(milliseconds: 1200));
      if (!mounted || demoQueue.isEmpty) break;
      final next = demoQueue.removeAt(0);
      await _send(next);
      if (turn['ended'] == true) break;
    }
  }

  void _ingestTranscript(Map<String, dynamic> snap) {
    final t = snap['transcript'];
    if (t is List) {
      transcript = t.map((e) => (e as Map).cast<String, dynamic>()).toList();
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (scrollCtrl.hasClients) {
        scrollCtrl.animateTo(scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send(String text) async {
    if (callId == null || text.trim().isEmpty || busy) return;
    setState(() => busy = true);
    try {
      final res = await api.utterance(callId: callId!, text: text.trim());
      turn = (res['turn'] as Map).cast<String, dynamic>();
      snapshot = (res['snapshot'] as Map).cast<String, dynamic>();
      _ingestTranscript(snapshot);
      inputCtrl.clear();
      _scrollToEnd();
    } catch (e) {
      setState(() => banner = 'Something went wrong - $e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lead = (snapshot['lead'] as Map?)?.cast<String, dynamic>() ?? {};
    final fields = (snapshot['fields'] as Map?)?.cast<String, dynamic>() ?? {};
    final progress = ((turn['journey_progress'] ?? snapshot['journey_progress']) as List?) ?? [];
    final state = turn['state']?.toString() ?? snapshot['state']?.toString() ?? 'Starting';
    final ended = turn['ended'] == true;
    final customerName =
        lead.isEmpty ? 'Customer' : '${lead['first_name'] ?? ''} ${lead['last_name'] ?? ''}'.trim();

    return Scaffold(
      backgroundColor: AppTheme.bg,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(customerName.isEmpty ? 'Recovery call' : customerName),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(child: _statusPill(ended ? 'Ended' : (live ? 'Live' : 'Idle'))),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (banner != null)
              Container(
                width: double.infinity,
                color: AppTheme.panelAlt,
                padding: const EdgeInsets.all(12),
                child: Text(banner!, style: TextStyle(color: AppTheme.accent)),
              ),
            _outcomeBanner(state, turn),
            if (fields.isNotEmpty || progress.isNotEmpty)
              _summaryStrip(fields, progress),
            Expanded(child: _transcriptView()),
            if (!ended) _composer(),
          ],
        ),
      ),
    );
  }

  Widget _statusPill(String label) {
    final color = label == 'Live' ? AppTheme.accent : AppTheme.muted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 12)),
    );
  }

  /// One plain sentence explaining how the call ended.
  Widget _outcomeBanner(String state, Map t) {
    String? message;
    Color color = AppTheme.text;

    if (state == 'COMPLETED' || state == 'ENDED' && t['receipt']?['accepted'] == true) {
      final ref = t['receipt']?['reference'];
      message = ref != null ? 'Completed - reference $ref' : 'Journey completed';
      color = AppTheme.accent;
    } else if (t['handoff_ticket_id'] != null) {
      message = 'Handed to a human colleague - waiting in the Agent Inbox';
      color = AppTheme.accent;
    } else if (state == 'DECLINED') {
      message = 'The customer declined. No further contact was made.';
      color = AppTheme.muted;
    } else if (state == 'ENDED' && (t['receipt'] != null && t['receipt']?['accepted'] != true)) {
      message = 'The journey could not be submitted - see the transcript below.';
      color = AppTheme.accent;
    }

    if (message == null) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Text(message, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
    );
  }

  /// What's already known, and how far along the journey is.
  Widget _summaryStrip(Map fields, List progress) {
    final done = progress.where((p) => (p as Map)['status'] == 'done').length;
    final total = progress.isEmpty ? 0 : progress.length;
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (total > 0)
            Text('$done of $total details collected',
                style: AppTheme.prose(13).copyWith(fontWeight: FontWeight.w600, color: AppTheme.text)),
          if (fields.isNotEmpty) ...[
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: fields.entries
                  .map((e) => Chip(
                        label: Text('${e.key.toString().replaceAll('_', ' ')}: ${e.value}',
                            style: const TextStyle(fontSize: 12)),
                        backgroundColor: AppTheme.panelAlt,
                        side: BorderSide.none,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _transcriptView() {
    if (transcript.isEmpty) {
      return Center(
        child: busy
            ? const CircularProgressIndicator()
            : Text('The conversation will appear here.', style: AppTheme.prose(14)),
      );
    }
    return ListView.builder(
      controller: scrollCtrl,
      padding: const EdgeInsets.all(16),
      itemCount: transcript.length,
      itemBuilder: (_, i) {
        final m = transcript[i];
        final role = '${m['role']}';
        final isAgent = role == 'assistant' || role == 'human_agent';
        final label = role == 'human_agent'
            ? 'Human'
            : role == 'assistant'
                ? 'AI'
                : 'Customer';
        return Align(
          alignment: isAgent ? Alignment.centerLeft : Alignment.centerRight,
          child: Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            constraints: const BoxConstraints(maxWidth: 480),
            decoration: BoxDecoration(
              color: isAgent ? AppTheme.panel : AppTheme.accent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: TextStyle(
                        fontSize: 11, fontWeight: FontWeight.w700, color: AppTheme.muted)),
                const SizedBox(height: 3),
                Text('${m['text']}', style: AppTheme.prose(14).copyWith(color: AppTheme.text)),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _composer() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: inputCtrl,
              onSubmitted: _send,
              decoration: const InputDecoration(hintText: 'Type what the customer says...'),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: busy ? null : () => _send(inputCtrl.text),
            child: const Text('Send'),
          ),
        ],
      ),
    );
  }
}
