import 'dart:async';

class BrowserVoiceService {
  bool listening = false;
  final _utteranceCtrl = StreamController<String>.broadcast();

  Stream<String> get utterances => _utteranceCtrl.stream;

  void speak(String text) {}

  void stopSpeaking() {}

  void startListening() {
    listening = false;
  }

  void stopListening() {
    listening = false;
  }

  void dispose() {
    _utteranceCtrl.close();
  }
}
