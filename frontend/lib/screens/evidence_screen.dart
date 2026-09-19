import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/api_client.dart';

/// Four things this build can prove live, that a slide can only assert.
/// Each fact is pulled fresh from the running backend - nothing here is a
/// screenshot or a canned number.
class EvidenceScreen extends StatefulWidget {
  const EvidenceScreen({super.key});

  @override
  State<EvidenceScreen> createState() => _EvidenceScreenState();
}

class _EvidenceScreenState extends State<EvidenceScreen> {
  final api = ApiClient();
  bool loading = true;
  String? error;

  Map<String, dynamic>? guard;
  Map<String, dynamic>? abTest;
  Map<String, dynamic>? evaluation;
  Map<String, dynamic>? cost;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final results = await Future.wait([
        api.hallucinationGuard(),
        api.abTestReport(),
        api.evaluationSuite(),
        api.costPerCall(),
      ]);
      if (!mounted) return;
      setState(() {
        guard = results[0];
        abTest = results[1];
        evaluation = results[2];
        cost = results[3];
      });
    } catch (e) {
      if (mounted) setState(() => error = 'Backend offline - start the API on :8000');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bg,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Evidence'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: loading ? null : _load),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : error != null
                    ? Center(child: Text(error!, style: AppTheme.prose(14)))
                    : ListView(
                        padding: const EdgeInsets.all(20),
                        children: [
                          Text('Things you can check, not take our word for',
                              style: AppTheme.heading(24)),
                          const SizedBox(height: 6),
                          Text(
                            'Every number below comes from the backend right now - press '
                            'refresh after running a demo and it will change.',
                            style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
                          ),
                          const SizedBox(height: 28),
                          _hallucinationCard(),
                          const SizedBox(height: 20),
                          _abTestCard(),
                          const SizedBox(height: 20),
                          _evaluationCard(),
                          const SizedBox(height: 20),
                          _costCard(),
                        ],
                      ),
          ),
        ),
      ),
    );
  }

  Widget _card({required String title, required Widget child}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppTheme.heading(16)),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }

  Widget _hallucinationCard() {
    final total = (guard?['summary']?['total_overrules'] as num?)?.toInt() ?? 0;
    final entries = (guard?['entries'] as List?) ?? [];
    return _card(
      title: 'Catching the model when it gets it wrong',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            total == 0
                ? "No disagreements yet this session. Run a demo call, then refresh - "
                  "the AI does sometimes mishear a field, and this is where it gets caught."
                : 'This session, the AI suggested the wrong answer $total time'
                    '${total == 1 ? '' : 's'}, and a rule caught it before it reached the payload.',
            style: AppTheme.prose(14),
          ),
          if (entries.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...entries.take(3).map((e) {
              final m = (e as Map).cast<String, dynamic>();
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  '"${m['customer_said']}" - the model said "${m['llm_suggested']}", '
                  'the rule kept "${m['rule_value']}"',
                  style: AppTheme.prose(13).copyWith(color: AppTheme.muted),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }

  Widget _abTestCard() {
    final experiments = (abTest?['experiments'] as List?) ?? [];
    return _card(
      title: 'Testing which question wording works better',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final raw in experiments) ...[
            Builder(builder: (_) {
              final e = (raw as Map).cast<String, dynamic>();
              final variants = (e['variants'] as Map).cast<String, dynamic>();
              final winner = (variants[e['winner']] as Map).cast<String, dynamic>();
              final loserKey = variants.keys.firstWhere((k) => k != e['winner']);
              final loser = (variants[loserKey] as Map).cast<String, dynamic>();
              final winRate = ((winner['first_try_capture_rate'] as num) * 100).round();
              final loseRate = ((loser['first_try_capture_rate'] as num) * 100).round();
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  '"${winner['script']}" got the answer right first try $winRate% of the '
                  'time, versus $loseRate% for "${loser['script']}".',
                  style: AppTheme.prose(14),
                ),
              );
            }),
          ],
          Text(
            'Based on a stated hypothesis about how each wording shifts answers, '
            'not live call data yet - see config/script_variants.json.',
            style: AppTheme.prose(12).copyWith(color: AppTheme.faint),
          ),
        ],
      ),
    );
  }

  Widget _evaluationCard() {
    final passed = (evaluation?['passed'] as num?)?.toInt() ?? 0;
    final total = (evaluation?['total'] as num?)?.toInt() ?? 0;
    return _card(
      title: 'Every scripted situation, checked automatically',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$passed of $total situations pass right now - a rude customer, a wrong '
            'answer, someone asking for a person, a declined call, and more. Run it '
            'again any time; it never depends on luck.',
            style: AppTheme.prose(14),
          ),
        ],
      ),
    );
  }

  Widget _costCard() {
    final ai = (cost?['ai_cost_per_call_usd'] as Map?)?.cast<String, dynamic>() ?? {};
    final usCost = ai['calling_a_us_number'];
    return _card(
      title: 'What a call actually costs to run',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            usCost != null
                ? 'About \$${(usCost as num).toStringAsFixed(3)} per call - mostly the '
                  'phone line itself; the AI\'s share is a fraction of a cent.'
                : 'Cost data unavailable.',
            style: AppTheme.prose(14),
          ),
          const SizedBox(height: 6),
          Text(
            'Real, dated prices from Groq and Twilio - see the note field at '
            '/api/economics/cost-per-call for sources. The human-agent comparison '
            'needs a real labour cost from CIMET before it means anything.',
            style: AppTheme.prose(12).copyWith(color: AppTheme.faint),
          ),
        ],
      ),
    );
  }
}
