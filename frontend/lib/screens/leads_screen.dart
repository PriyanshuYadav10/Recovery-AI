import 'dart:async';
import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;
import '../theme/app_theme.dart';
import '../theme/handout.dart';
import '../services/api_client.dart';
import '../services/web_file_picker.dart';

/// A CRM-style workspace: upload a sheet of leads, see them as a callable
/// list, call one straight from the row, watch the transcript live in the
/// same screen, and the outcome is saved back onto that row - by the
/// backend, not this screen - so it's still there after a refresh.
class LeadsScreen extends StatefulWidget {
  const LeadsScreen({super.key});

  @override
  State<LeadsScreen> createState() => _LeadsScreenState();
}

class _LeadsScreenState extends State<LeadsScreen> {
  final api = ApiClient();
  final numberCtrl = TextEditingController();
  final transcriptScroll = ScrollController();

  List<Map<String, dynamic>> leads = [];
  bool loadingLeads = false;
  bool uploading = false;
  String? listError;

  String? activeLeadId;
  String? activeCallId;
  Map<String, dynamic> activeSnapshot = {};
  List<Map<String, dynamic>> activeTranscript = [];
  bool callBusy = false;
  String? callError;
  Timer? pollTimer;

  @override
  void initState() {
    super.initState();
    try {
      numberCtrl.text = web.window.localStorage.getItem('verified_number') ?? '';
    } catch (_) {}
    _loadLeads();
  }

  @override
  void dispose() {
    pollTimer?.cancel();
    numberCtrl.dispose();
    transcriptScroll.dispose();
    super.dispose();
  }

  Future<void> _loadLeads() async {
    setState(() => loadingLeads = true);
    try {
      final data = await api.uploadedLeads();
      if (!mounted) return;
      setState(() {
        leads = data.cast<Map>().map((e) => e.cast<String, dynamic>()).toList();
        listError = null;
      });
    } catch (e) {
      if (mounted) setState(() => listError = 'Could not load leads - $e');
    } finally {
      if (mounted) setState(() => loadingLeads = false);
    }
  }

  Future<void> _pickAndUpload() async {
    final file = await pickLeadSheetFile();
    if (file == null) return;
    setState(() {
      uploading = true;
      listError = null;
    });
    try {
      final res = await api.uploadLeadSheet(filename: file.name, bytes: file.bytes);
      if (!mounted) return;
      setState(() {
        leads = (res['leads'] as List).cast<Map>().map((e) => e.cast<String, dynamic>()).toList();
      });
    } catch (e) {
      if (mounted) setState(() => listError = 'Upload failed - $e');
    } finally {
      if (mounted) setState(() => uploading = false);
    }
  }

  Future<void> _loadSampleLeads() async {
    setState(() {
      uploading = true;
      listError = null;
    });
    try {
      final res = await api.uploadSampleLeads();
      if (!mounted) return;
      setState(() {
        leads = (res['leads'] as List).cast<Map>().map((e) => e.cast<String, dynamic>()).toList();
      });
    } catch (e) {
      if (mounted) setState(() => listError = 'Could not load the demo leads - $e');
    } finally {
      if (mounted) setState(() => uploading = false);
    }
  }

  Future<void> _clearAll() async {
    try {
      await api.clearUploadedLeads();
      await _loadLeads();
      setState(() {
        activeLeadId = null;
        activeCallId = null;
      });
    } catch (e) {
      setState(() => listError = 'Could not clear the list - $e');
    }
  }

  bool _validNumber(String phone) {
    final digitsOnly = phone.trim().replaceAll(RegExp(r'[^\d+]'), '');
    return digitsOnly.startsWith('+') && digitsOnly.length >= 8;
  }

  Future<void> _callLead(Map<String, dynamic> lead) async {
    final phone = numberCtrl.text.trim();
    if (!_validNumber(phone)) {
      setState(() => callError =
          'Enter your verified number with a country code first, e.g. +91XXXXXXXXXX.');
      return;
    }
    try {
      web.window.localStorage.setItem('verified_number', phone);
    } catch (_) {}

    pollTimer?.cancel();
    setState(() {
      activeLeadId = lead['lead_id'] as String;
      activeCallId = null;
      activeSnapshot = {};
      activeTranscript = [];
      callBusy = true;
      callError = null;
    });

    try {
      final res = await api.dialReal(leadId: lead['lead_id'] as String, phone: phone);
      if (res['dialled'] == false) {
        setState(() {
          callBusy = false;
          callError = 'Blocked before dialling: ${res['blocked_by']} - '
              '${res['detail']?['reason'] ?? 'not eligible'}';
        });
        await _loadLeads();
        return;
      }
      final dialResult = (res['dial_result'] as Map?) ?? {};
      final status = dialResult['status'];
      if (status == 'bridge_unavailable' || status == 'dial_failed') {
        setState(() {
          callBusy = false;
          callError = 'Twilio bridge did not accept the call: ${dialResult['error'] ?? status}.';
        });
        await _loadLeads();
        return;
      }
      final callId = res['call_id'] as String?;
      if (callId == null) {
        setState(() {
          callBusy = false;
          callError = 'No call_id returned - unexpected response.';
        });
        return;
      }
      setState(() => activeCallId = callId);
      await _pollActiveCall();
      pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _pollActiveCall());
    } catch (e) {
      setState(() {
        callBusy = false;
        callError = 'Dial failed - $e';
      });
      await _loadLeads();
    }
  }

  Future<void> _pollActiveCall() async {
    final id = activeCallId;
    if (id == null || !mounted) return;
    try {
      final snap = await api.getCall(id);
      if (!mounted) return;
      setState(() {
        activeSnapshot = snap;
        final t = snap['transcript'];
        if (t is List) {
          activeTranscript = t.cast<Map>().map((e) => e.cast<String, dynamic>()).toList();
        }
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (transcriptScroll.hasClients) {
          transcriptScroll.animateTo(
            transcriptScroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeOut,
          );
        }
      });
      final state = snap['state'];
      if (state == 'ENDED' || state == 'HANDOFF') {
        pollTimer?.cancel();
        setState(() => callBusy = false);
        await _loadLeads();
      }
    } catch (e) {
      if (mounted) setState(() => callError = 'Lost contact with the call - $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bg,
      body: SafeArea(
        child: Column(
          children: [
            _header(),
            if (listError != null) _banner(listError!),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(flex: 4, child: _leadsPanel()),
                    const SizedBox(width: 14),
                    Expanded(flex: 6, child: _callPanel()),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _banner(String text) => Container(
        width: double.infinity,
        color: AppTheme.warn.withValues(alpha: 0.14),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
        child: Text(text, style: const TextStyle(color: AppTheme.warn, fontSize: 12.5)),
      );

  Widget _header() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back_ios_new, size: 16),
          ),
          const SizedBox(width: 4),
          Text('Lead call list', style: AppTheme.heading(19)),
          const SizedBox(width: 14),
          Text('${leads.length} lead${leads.length == 1 ? '' : 's'}',
              style: AppTheme.prose(13).copyWith(color: AppTheme.muted)),
          const SizedBox(width: 18),
          OutlinedButton.icon(
            onPressed: uploading ? null : _pickAndUpload,
            icon: uploading
                ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.upload_file, size: 16),
            label: Text(uploading ? 'Uploading...' : 'Upload sheet'),
          ),
          const SizedBox(width: 8),
          TextButton.icon(
            onPressed: uploading ? null : _loadSampleLeads,
            icon: const Icon(Icons.auto_awesome, size: 16),
            label: const Text('Load demo leads'),
          ),
          if (leads.isNotEmpty) ...[
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: _clearAll,
              icon: const Icon(Icons.delete_outline, size: 16),
              label: const Text('Clear list'),
            ),
          ],
          const Spacer(),
          SizedBox(
            width: 230,
            child: TextField(
              controller: numberCtrl,
              style: AppTheme.prose(13),
              decoration: const InputDecoration(
                isDense: true,
                prefixIcon: Icon(Icons.call, size: 16),
                hintText: 'Your verified number, +91...',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _leadsPanel() {
    return _panel(
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppTheme.line))),
            child: const MonoLabel('LEADS'),
          ),
          Expanded(
            child: leads.isEmpty
                ? _emptyLeadsState()
                : ListView.separated(
                    padding: const EdgeInsets.all(10),
                    itemCount: leads.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (_, i) => _leadRow(leads[i]),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _emptyLeadsState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.table_rows_outlined, size: 34, color: AppTheme.faint),
            const SizedBox(height: 12),
            Text('No leads yet', style: AppTheme.heading(15)),
            const SizedBox(height: 6),
            Text(
              'Upload a CSV or Excel sheet with name, phone and email\ncolumns to build your call list.',
              textAlign: TextAlign.center,
              style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              alignment: WrapAlignment.center,
              children: [
                FilledButton.icon(
                  onPressed: uploading ? null : _pickAndUpload,
                  icon: const Icon(Icons.upload_file, size: 16),
                  label: const Text('Upload sheet'),
                ),
                OutlinedButton.icon(
                  onPressed: uploading ? null : _loadSampleLeads,
                  icon: const Icon(Icons.auto_awesome, size: 16),
                  label: const Text('Load demo leads'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _leadRow(Map<String, dynamic> lead) {
    final leadId = lead['lead_id'] as String;
    final isActive = leadId == activeLeadId;
    final status = '${lead['status'] ?? 'NOT_CALLED'}';
    final name = '${lead['first_name'] ?? ''} ${lead['last_name'] ?? ''}'.trim();
    final initials = name.isEmpty
        ? '?'
        : name.trim().split(RegExp(r'\s+')).take(2).map((s) => s[0]).join().toUpperCase();
    final calling = isActive && callBusy;

    return Material(
      color: isActive ? AppTheme.panelAlt : AppTheme.panel,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => setState(() {
          activeLeadId = leadId;
          if (!calling) {
            activeCallId = lead['last_call_id'] as String?;
            activeSnapshot = {};
            activeTranscript = [];
            callError = null;
            if (activeCallId != null) _loadReplayForRow(activeCallId!);
          }
        }),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: isActive ? AppTheme.accent.withValues(alpha: 0.5) : AppTheme.line),
          ),
          child: Row(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: AppTheme.panelAlt,
                child: Text(initials, style: AppTheme.mono(10, color: AppTheme.text, tracking: 0.5)),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name.isEmpty ? 'Unknown' : name,
                        style: AppTheme.prose(13.5).copyWith(color: AppTheme.text),
                        overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text('${lead['phone'] ?? ''}',
                        style: AppTheme.prose(11.5).copyWith(color: AppTheme.muted)),
                    const SizedBox(height: 4),
                    _statusChip(status, pulsing: calling),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              IconButton(
                tooltip: 'Call',
                onPressed: callBusy ? null : () => _callLead(lead),
                icon: Icon(Icons.call,
                    size: 18, color: callBusy ? AppTheme.faint : AppTheme.accent),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Selecting a lead that already has a call attached shows that call's
  /// transcript again (read-only, via replay) instead of an empty panel.
  Future<void> _loadReplayForRow(String callId) async {
    try {
      final data = await api.replay(callId);
      if (!mounted || activeCallId != callId) return;
      setState(() {
        final t = data['transcript'];
        activeTranscript =
            t is List ? t.cast<Map>().map((e) => e.cast<String, dynamic>()).toList() : [];
      });
    } catch (_) {}
  }

  Widget _callPanel() {
    if (activeLeadId == null) {
      return _panel(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.forum_outlined, size: 34, color: AppTheme.faint),
                const SizedBox(height: 12),
                Text('Select a lead and hit call', style: AppTheme.heading(15)),
                const SizedBox(height: 6),
                Text(
                  'The live transcript shows up here while the call runs, and\n'
                  'the outcome is saved back onto that lead once it ends.',
                  textAlign: TextAlign.center,
                  style: AppTheme.prose(12.5).copyWith(color: AppTheme.muted),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final lead = leads.firstWhere((l) => l['lead_id'] == activeLeadId, orElse: () => {});
    final name = '${lead['first_name'] ?? ''} ${lead['last_name'] ?? ''}'.trim();
    final state = activeSnapshot['state']?.toString();
    final ended = state == 'ENDED' || state == 'HANDOFF';
    final ticketId = activeSnapshot['handoff_ticket_id'];

    return _panel(
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppTheme.line))),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name.isEmpty ? (activeLeadId ?? '') : name,
                          style: AppTheme.heading(14)),
                      Text('${lead['phone'] ?? ''}',
                          style: AppTheme.prose(11.5).copyWith(color: AppTheme.muted)),
                    ],
                  ),
                ),
                if (callBusy)
                  Row(children: const [
                    SizedBox(
                        width: 10, height: 10, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: 7),
                    MonoLabel('LIVE', color: AppTheme.accent, size: 9),
                  ])
                else if (state != null)
                  _statusChip('${lead['status'] ?? state}'),
              ],
            ),
          ),
          if (callError != null)
            Container(
              width: double.infinity,
              color: AppTheme.warn.withValues(alpha: 0.12),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
              child: Text(callError!, style: const TextStyle(color: AppTheme.warn, fontSize: 12.5)),
            ),
          Expanded(
            child: activeTranscript.isEmpty
                ? Center(
                    child: Text(
                      callBusy ? 'Ringing...' : 'No transcript yet.',
                      style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
                    ),
                  )
                : ListView.builder(
                    controller: transcriptScroll,
                    padding: const EdgeInsets.all(14),
                    itemCount: activeTranscript.length,
                    itemBuilder: (_, i) {
                      final m = activeTranscript[i];
                      final role = '${m['role']}';
                      final isAi = role == 'assistant';
                      final tag = isAi
                          ? 'AI AGENT'
                          : role == 'human_agent'
                              ? 'HUMAN'
                              : 'CUSTOMER';
                      final tagColour =
                          isAi ? AppTheme.accent : (role == 'human_agent' ? AppTheme.text : AppTheme.muted);
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            MonoLabel(tag, color: tagColour, size: 9),
                            const SizedBox(height: 4),
                            Text('${m['text']}',
                                style: AppTheme.prose(13).copyWith(
                                    color: isAi ? AppTheme.text : AppTheme.body)),
                          ],
                        ),
                      );
                    },
                  ),
          ),
          if (ended)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: AppTheme.line))),
              child: Row(
                children: [
                  Icon(state == 'HANDOFF' ? Icons.headset_mic : Icons.check_circle,
                      size: 16, color: AppTheme.accent),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      state == 'HANDOFF'
                          ? 'Escalated to a human agent - status saved to the list.'
                          : 'Call ended - status saved to the list.',
                      style: AppTheme.prose(12.5).copyWith(color: AppTheme.text),
                    ),
                  ),
                  if (ticketId != null)
                    TextButton(
                      onPressed: () => Navigator.of(context).pushNamed('/inbox'),
                      child: const Text('Open inbox'),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _statusChip(String status, {bool pulsing = false}) {
    final color = _statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (pulsing) ...[
            Container(width: 6, height: 6, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
            const SizedBox(width: 5),
          ],
          Text(_statusLabel(status),
              style: AppTheme.mono(8.5, color: color, tracking: 1, weight: FontWeight.w700)),
        ],
      ),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'CALLING':
        return AppTheme.accent;
      case 'COMPLETED':
        return const Color(0xFF0A7A48); // darkened for AA contrast on a light background
      case 'HANDOFF':
        return const Color(0xFF9A6400); // darkened for AA contrast on a light background
      case 'DECLINED':
        return AppTheme.muted;
      case 'BLOCKED_DNC':
      case 'FAILED':
        return const Color(0xFFC4302C); // darkened for AA contrast on a light background
      default:
        return AppTheme.faint;
    }
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'NOT_CALLED':
        return 'NOT CALLED';
      case 'CALLING':
        return 'CALLING';
      case 'COMPLETED':
        return 'COMPLETED';
      case 'HANDOFF':
        return 'ESCALATED';
      case 'DECLINED':
        return 'DECLINED';
      case 'BLOCKED_DNC':
        return 'BLOCKED · DNC';
      case 'FAILED':
        return 'CALL FAILED';
      default:
        return status;
    }
  }

  Widget _panel({required Widget child}) {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: child,
    );
  }
}
