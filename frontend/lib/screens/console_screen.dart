import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../theme/handout.dart';
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
    _scrollToEnd();
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
        titleSpacing: 0,
        title: Row(
          children: [
            _avatar(customerName),
            const SizedBox(width: 12),
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(customerName.isEmpty ? 'Recovery call' : customerName,
                    style: AppTheme.heading(15)),
                Text(lead['lead_id']?.toString() ?? 'Demo call',
                    style: AppTheme.prose(11.5).copyWith(color: AppTheme.muted)),
              ],
            ),
          ],
        ),
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
            if (callId != null) _ledgerLink(),
            if (fields.isNotEmpty || progress.isNotEmpty) _summaryStrip(fields, progress),
            Expanded(child: _transcriptView()),
            if (!ended) _composer(),
          ],
        ),
      ),
    );
  }

  Widget _avatar(String name) {
    final initials = _initials(name);
    return Container(
      width: 32,
      height: 32,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppTheme.accent.withValues(alpha: 0.12),
        shape: BoxShape.circle,
      ),
      child: Text(initials,
          style: AppTheme.mono(12, color: AppTheme.accent, tracking: 0, weight: FontWeight.w700)),
    );
  }

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }

  Widget _statusPill(String label) {
    final color = label == 'Live' ? AppTheme.accent : AppTheme.muted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (label == 'Live') ...[
            Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
          ],
          Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 12)),
        ],
      ),
    );
  }

  /// One plain sentence explaining how the call ended, with an icon that
  /// matches - dressed as the same raised callout card used on the landing
  /// page, so this screen reads as part of the same product.
  Widget _outcomeBanner(String state, Map t) {
    String? message;
    Color color = AppTheme.text;
    IconData icon = Icons.info_outline;

    if (state == 'COMPLETED' || state == 'ENDED' && t['receipt']?['accepted'] == true) {
      final ref = t['receipt']?['reference'];
      message = ref != null ? 'Completed - reference $ref' : 'Journey completed';
      color = AppTheme.accent;
      icon = Icons.check_circle;
    } else if (t['handoff_ticket_id'] != null) {
      message = 'Handed to a human colleague - waiting in the Agent Inbox';
      color = AppTheme.accent;
      icon = Icons.support_agent;
    } else if (state == 'DECLINED') {
      message = 'The customer declined. No further contact was made.';
      color = AppTheme.muted;
      icon = Icons.block;
    } else if (state == 'ENDED' && (t['receipt'] != null && t['receipt']?['accepted'] != true)) {
      message = 'The journey could not be submitted - see the transcript below.';
      color = AppTheme.accent;
      icon = Icons.error_outline;
    }

    if (message == null) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(12),
        boxShadow: AppTheme.cardShadow,
        border: Border(left: BorderSide(color: color, width: 4)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 19, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Text(message, style: AppTheme.prose(14).copyWith(color: AppTheme.text, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  /// Opens the compliance ledger for this call - a small link, not a
  /// button, because it's a background guarantee rather than a next step.
  Widget _ledgerLink() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
        child: InkWell(
          onTap: () => showDialog(
            context: context,
            builder: (_) => _LedgerDialog(api: api, callId: callId!),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.verified_outlined, size: 15, color: AppTheme.muted),
              const SizedBox(width: 6),
              Text('View compliance ledger',
                  style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }

  /// What's already known, and how far along the journey is - a real
  /// progress bar rather than just a fraction in prose, plus each captured
  /// detail as a small key/value pill instead of a default Material chip.
  Widget _summaryStrip(Map fields, List progress) {
    final done = progress.where((p) => (p as Map)['status'] == 'done').length;
    final total = progress.isEmpty ? 0 : progress.length;
    final pct = total > 0 ? done / total : 0.0;
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(12),
        boxShadow: AppTheme.cardShadow,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (total > 0) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('$done of $total details collected',
                    style: AppTheme.prose(13).copyWith(fontWeight: FontWeight.w600, color: AppTheme.text)),
                Text('${(pct * 100).round()}%',
                    style: AppTheme.mono(11, color: AppTheme.accent, weight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: pct),
                duration: const Duration(milliseconds: 450),
                curve: Curves.easeOutCubic,
                builder: (context, v, _) => LinearProgressIndicator(
                  value: v,
                  minHeight: 6,
                  backgroundColor: AppTheme.line,
                  color: AppTheme.accent,
                ),
              ),
            ),
          ],
          if (fields.isNotEmpty) ...[
            SizedBox(height: total > 0 ? 14 : 0),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: fields.entries.map((e) => _fieldPill(e.key.toString(), '${e.value}')).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _fieldPill(String key, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppTheme.panelAlt,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.line),
      ),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(text: '${key.replaceAll('_', ' ')}  ', style: AppTheme.mono(10.5, color: AppTheme.label)),
            TextSpan(text: value, style: AppTheme.prose(12).copyWith(color: AppTheme.text, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }

  Widget _transcriptView() {
    if (transcript.isEmpty) {
      return Center(
        child: busy
            ? _typingBubble(align: Alignment.center)
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 52,
                    height: 52,
                    decoration: BoxDecoration(color: AppTheme.panel, shape: BoxShape.circle),
                    child: Icon(Icons.phone_in_talk_outlined, color: AppTheme.faint, size: 24),
                  ),
                  const SizedBox(height: 14),
                  Text('The conversation will appear here.', style: AppTheme.prose(14)),
                ],
              ),
      );
    }
    final showTyping = busy && live && turn['ended'] != true;
    final itemCount = transcript.length + (showTyping ? 1 : 0);
    return ListView.builder(
      controller: scrollCtrl,
      padding: const EdgeInsets.all(16),
      itemCount: itemCount,
      itemBuilder: (_, i) {
        if (i == transcript.length) {
          return Align(alignment: Alignment.centerLeft, child: _typingBubble());
        }
        final m = transcript[i];
        final role = '${m['role']}';
        final isAgent = role == 'assistant' || role == 'human_agent';
        final label = role == 'human_agent'
            ? 'Human'
            : role == 'assistant'
                ? 'AI'
                : 'Customer';
        final bubbleColor = isAgent ? AppTheme.panel : AppTheme.accent.withValues(alpha: 0.10);
        final radius = BorderRadius.only(
          topLeft: Radius.circular(isAgent ? 4 : 14),
          topRight: Radius.circular(isAgent ? 14 : 4),
          bottomLeft: const Radius.circular(14),
          bottomRight: const Radius.circular(14),
        );
        final bubble = Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          constraints: const BoxConstraints(maxWidth: 460),
          decoration: BoxDecoration(color: bubbleColor, borderRadius: radius),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppTheme.muted)),
              const SizedBox(height: 3),
              Text('${m['text']}', style: AppTheme.prose(14).copyWith(color: AppTheme.text)),
            ],
          ),
        );
        final avatar = _roleAvatar(role);
        final row = isAgent
            ? [avatar, const SizedBox(width: 8), Flexible(child: bubble)]
            : [Flexible(child: bubble), const SizedBox(width: 8), avatar];
        return Align(
          alignment: isAgent ? Alignment.centerLeft : Alignment.centerRight,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: row,
          ),
        );
      },
    );
  }

  Widget _roleAvatar(String role) {
    final isHuman = role == 'human_agent';
    final isAgent = isHuman || role == 'assistant';
    return Container(
      width: 26,
      height: 26,
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: isAgent ? AppTheme.accent.withValues(alpha: 0.14) : AppTheme.panelAlt,
        shape: BoxShape.circle,
      ),
      child: Icon(
        isHuman ? Icons.support_agent : (isAgent ? Icons.auto_awesome : Icons.person),
        size: 14,
        color: isAgent ? AppTheme.accent : AppTheme.muted,
      ),
    );
  }

  Widget _typingBubble({Alignment align = Alignment.centerLeft}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(14)),
      child: const _TypingDots(),
    );
  }

  Widget _composer() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppTheme.panel,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppTheme.line),
              ),
              child: TextField(
                controller: inputCtrl,
                onSubmitted: _send,
                minLines: 1,
                maxLines: 4,
                style: AppTheme.prose(14),
                decoration: InputDecoration(
                  hintText: 'Type what the customer says...',
                  border: InputBorder.none,
                  filled: false,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          HoverLift(
            borderRadius: 24,
            child: Material(
              color: busy ? AppTheme.panelAlt : AppTheme.accent,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: busy ? null : () => _send(inputCtrl.text),
                child: Container(
                  width: 46,
                  height: 46,
                  alignment: Alignment.center,
                  child: Icon(Icons.arrow_upward, color: busy ? AppTheme.faint : AppTheme.ink, size: 20),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Three dots that fade in a stagger, like a messaging app's "typing..." -
/// shown while waiting for the agent's next line, so the pause reads as
/// "thinking" rather than a stalled screen.
class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < 3; i++) ...[
              if (i > 0) const SizedBox(width: 5),
              _dot(i),
            ],
          ],
        );
      },
    );
  }

  Widget _dot(int i) {
    final t = (_controller.value + (i * 0.22)) % 1.0;
    final opacity = 0.25 + 0.75 * (t < 0.5 ? t * 2 : (1 - t) * 2);
    return Opacity(
      opacity: opacity.clamp(0.25, 1.0),
      child: Container(
        width: 7,
        height: 7,
        decoration: const BoxDecoration(color: AppTheme.accent, shape: BoxShape.circle),
      ),
    );
  }
}

/// Every consent, guardrail and field decision this call made, hash-chained
/// so the compliance trail can be verified rather than just trusted - and a
/// live "simulate tampering" button that proves the point instead of
/// stating it: edit one record after the fact and watch the chain break,
/// with the exact broken record identified.
class _LedgerDialog extends StatefulWidget {
  const _LedgerDialog({required this.api, required this.callId});

  final ApiClient api;
  final String callId;

  @override
  State<_LedgerDialog> createState() => _LedgerDialogState();
}

class _LedgerDialogState extends State<_LedgerDialog> {
  static const _verifiedColor = Color(0xFF0A7A48); // darkened for AA contrast on a light background
  static const _brokenColor = Color(0xFFC4302C); // darkened for AA contrast on a light background

  bool loading = true;
  bool tamperedView = false;
  String? error;
  List<dynamic> ledger = [];
  Map<String, dynamic> verification = {};
  int? tamperedIndex;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      error = null;
      tamperedView = false;
      tamperedIndex = null;
    });
    try {
      final res = await widget.api.callLedger(widget.callId);
      setState(() {
        ledger = res['ledger'] as List;
        verification = (res['verification'] as Map).cast<String, dynamic>();
      });
    } catch (e) {
      setState(() => error = 'Could not load the ledger - $e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _simulateTamper() async {
    setState(() => loading = true);
    try {
      final res = await widget.api.tamperLedgerDemo(widget.callId);
      setState(() {
        ledger = res['ledger'] as List;
        verification = (res['verification'] as Map).cast<String, dynamic>();
        tamperedIndex = res['tampered_index'] as int?;
        tamperedView = true;
      });
    } catch (e) {
      setState(() => error = 'Could not run the tamper demo - $e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final valid = verification['valid'] == true;
    final color = valid ? _verifiedColor : _brokenColor;

    return Dialog(
      backgroundColor: AppTheme.bg,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520, maxHeight: 640),
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Compliance ledger', style: AppTheme.heading(18)),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                'Every consent, guardrail and field decision in this call, hash-chained. '
                'Edit one after the fact and the chain visibly breaks.',
                style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
              ),
              const SizedBox(height: 16),
              if (loading) const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator())),
              if (error != null) Text(error!, style: TextStyle(color: AppTheme.accent)),
              if (!loading && error == null) ...[
                AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: color.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      Icon(valid ? Icons.verified : Icons.gpp_bad, size: 18, color: color),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          valid
                              ? 'Verified - ${verification['record_count']} records, nothing altered'
                              : verification['reason']?.toString() ?? 'Chain broken',
                          style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Expanded(
                  child: ListView.builder(
                    itemCount: ledger.length,
                    itemBuilder: (_, i) {
                      final r = (ledger[i] as Map).cast<String, dynamic>();
                      final isBroken = verification['broken_at'] == i;
                      final isEdited = tamperedIndex == i;
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: isBroken ? _brokenColor.withValues(alpha: 0.06) : AppTheme.panel,
                          borderRadius: BorderRadius.circular(10),
                          border: isBroken ? Border.all(color: _brokenColor.withValues(alpha: 0.4)) : null,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                MonoLabel('#${r['index']}', size: 10),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text('${r['event']}',
                                      style: AppTheme.prose(13).copyWith(fontWeight: FontWeight.w700, color: AppTheme.text)),
                                ),
                                if (isEdited)
                                  Icon(Icons.edit, size: 13, color: _brokenColor)
                                else if (isBroken)
                                  Icon(Icons.link_off, size: 13, color: _brokenColor),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text('hash ${_short(r['hash'])}  ·  prev ${_short(r['prev_hash'])}',
                                style: AppTheme.mono(10, color: AppTheme.faint)),
                          ],
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: tamperedView ? _load : _simulateTamper,
                        icon: Icon(tamperedView ? Icons.restart_alt : Icons.science_outlined, size: 16),
                        label: Text(tamperedView ? 'Restore the real chain' : 'Simulate tampering'),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _short(dynamic hash) {
    final s = '$hash';
    return s.length > 10 ? '${s.substring(0, 10)}…' : s;
  }
}
