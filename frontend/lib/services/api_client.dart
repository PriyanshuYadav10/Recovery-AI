import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiClient {
  ApiClient({this.baseUrl = 'http://127.0.0.1:8000'});

  final String baseUrl;

  Uri _u(String path) => Uri.parse('$baseUrl$path');

  Future<Map<String, dynamic>> health() async {
    final r = await http.get(_u('/api/health'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> leads() async {
    final r = await http.get(_u('/api/leads'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  // ---- uploaded lead sheets (CRM list) -----------------------------------

  /// Loads a bundled demo lead sheet with one click, no file picker needed.
  Future<Map<String, dynamic>> uploadSampleLeads() async {
    final r = await http.post(_u('/api/leads/upload-sample'));
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Uploads a CSV/XLSX of leads. Re-uploading the same lead_id refreshes
  /// contact details without resetting that lead's call status.
  Future<Map<String, dynamic>> uploadLeadSheet({
    required String filename,
    required List<int> bytes,
  }) async {
    final req = http.MultipartRequest('POST', _u('/api/leads/upload'))
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) throw Exception(body);
    return jsonDecode(body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> uploadedLeads() async {
    final r = await http.get(_u('/api/leads/uploaded'));
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<void> deleteUploadedLead(String leadId) async {
    final r = await http.delete(_u('/api/leads/uploaded/$leadId'));
    if (r.statusCode >= 400) throw Exception(r.body);
  }

  Future<void> clearUploadedLeads() async {
    final r = await http.delete(_u('/api/leads/uploaded'));
    if (r.statusCode >= 400) throw Exception(r.body);
  }

  Future<Map<String, dynamic>> metrics() async {
    final r = await http.get(_u('/api/metrics'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> startCall({
    required String leadId,
    String voiceMode = 'BROWSER',
    String? scenario,
  }) async {
    final r = await http.post(
      _u('/api/calls/start'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'lead_id': leadId,
        'voice_mode': voiceMode,
        if (scenario != null) 'scenario': scenario,
      }),
    );
    if (r.statusCode >= 400) {
      throw Exception(r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> utterance({
    required String callId,
    required String text,
    double speechConfidence = 0.95,
  }) async {
    final r = await http.post(
      _u('/api/calls/utterance'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'call_id': callId,
        'text': text,
        'speech_confidence': speechConfidence,
      }),
    );
    if (r.statusCode >= 400) {
      throw Exception(r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Places a REAL outbound phone call via the Twilio bridge. [phone] is
  /// the actual number to ring; the lead's own (synthetic) contact details
  /// are still used for journey context, just not for dialling.
  Future<Map<String, dynamic>> dialReal({
    required String leadId,
    required String phone,
  }) async {
    final r = await http.post(
      _u('/api/calls/dial'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'lead_id': leadId, 'voice_mode': 'TWILIO', 'phone': phone}),
    );
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> runDemo(String scenario) async {
    final r = await http.post(_u('/api/demos/$scenario/run'));
    if (r.statusCode >= 400) {
      throw Exception(r.body);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// The live snapshot for a call already in progress (e.g. a real phone
  /// call, driven by the Twilio bridge rather than this app). Used to watch
  /// a call happen without having started it from this screen.
  Future<Map<String, dynamic>> getCall(String callId) async {
    final r = await http.get(_u('/api/calls/$callId'));
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> replay(String callId) async {
    final r = await http.get(_u('/api/calls/$callId/replay'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> baseline() async {
    final r = await http.get(_u('/api/baseline'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> submissions() async {
    final r = await http.get(_u('/api/submissions'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> prioritisedLeads() async {
    final r = await http.get(_u('/api/leads/prioritised'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> modelStatus() async {
    final r = await http.get(_u('/api/model/status'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  // ---- agent inbox -------------------------------------------------------

  Future<Map<String, dynamic>> handoffs({String? status}) async {
    final q = status == null ? '' : '?status=$status';
    final r = await http.get(_u('/api/handoffs$q'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> claimHandoff(String ticketId, String agentName) async {
    final r = await http.post(
      _u('/api/handoffs/$ticketId/claim'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'agent_name': agentName}),
    );
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> handoffMessage(String ticketId, String text) async {
    final r = await http.post(
      _u('/api/handoffs/$ticketId/message'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'role': 'human_agent', 'text': text}),
    );
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> resolveHandoff(String ticketId, String resolution) async {
    final r = await http.post(
      _u('/api/handoffs/$ticketId/resolve'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'resolution': resolution}),
    );
    if (r.statusCode >= 400) throw Exception(r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }
}
