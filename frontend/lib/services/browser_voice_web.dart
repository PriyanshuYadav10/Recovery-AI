import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'package:web/web.dart' as web;

/// Zero-cost browser voice via SpeechSynthesis + optional SpeechRecognition.
class BrowserVoiceService {
  bool listening = false;
  final _utteranceCtrl = StreamController<String>.broadcast();
  JSAny? _rec;

  Stream<String> get utterances => _utteranceCtrl.stream;

  void speak(String text) {
    try {
      final synth = web.window.speechSynthesis;
      synth.cancel();
      final u = web.SpeechSynthesisUtterance(text);
      u.rate = 1.02;
      synth.speak(u);
    } catch (_) {}
  }

  void stopSpeaking() {
    try {
      web.window.speechSynthesis.cancel();
    } catch (_) {}
  }

  void startListening() {
    stopSpeaking();
    try {
      final ctor = web.window.getProperty('webkitSpeechRecognition'.toJS) ??
          web.window.getProperty('SpeechRecognition'.toJS);
      if (ctor == null) {
        listening = false;
        return;
      }
      final rec = (ctor as JSFunction).callAsConstructor();
      rec.setProperty('lang'.toJS, 'en-AU'.toJS);
      rec.setProperty('continuous'.toJS, false.toJS);
      rec.setProperty('interimResults'.toJS, false.toJS);
      rec.setProperty(
        'onresult'.toJS,
        ((JSAny event) {
          try {
            final results = (event as JSObject).getProperty('results'.toJS);
            final first = (results as JSObject).callMethod('item'.toJS, 0.toJS);
            final alt = (first as JSObject).callMethod('item'.toJS, 0.toJS);
            final transcript =
                (alt as JSObject).getProperty('transcript'.toJS)?.dartify();
            if (transcript is String && transcript.trim().isNotEmpty) {
              _utteranceCtrl.add(transcript.trim());
            }
          } catch (_) {}
        }).toJS,
      );
      rec.setProperty(
        'onend'.toJS,
        ((JSAny _) {
          listening = false;
        }).toJS,
      );
      _rec = rec;
      listening = true;
      (rec as JSObject).callMethod('start'.toJS);
    } catch (_) {
      listening = false;
    }
  }

  void stopListening() {
    try {
      (_rec as JSObject?)?.callMethod('stop'.toJS);
    } catch (_) {}
    listening = false;
  }

  void dispose() {
    stopListening();
    stopSpeaking();
    _utteranceCtrl.close();
  }
}
