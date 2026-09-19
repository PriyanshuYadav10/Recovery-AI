import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';
import 'package:web/web.dart' as web;

class PickedSheetFile {
  PickedSheetFile(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

/// Opens the browser's native file picker restricted to CSV/XLSX and
/// resolves with the picked file's bytes, or null if the user cancelled.
Future<PickedSheetFile?> pickLeadSheetFile() {
  final completer = Completer<PickedSheetFile?>();
  final input = web.HTMLInputElement()
    ..type = 'file'
    ..accept = '.csv,.xlsx,.xls';

  input.onchange = (web.Event _) {
    final file = input.files?.item(0);
    if (file == null) {
      completer.complete(null);
      return;
    }
    final reader = web.FileReader();
    reader.onload = (web.Event _) {
      final buffer = reader.result as JSArrayBuffer;
      completer.complete(PickedSheetFile(file.name, buffer.toDart.asUint8List()));
    }.toJS;
    reader.onerror = ((web.Event _) => completer.complete(null)).toJS;
    reader.readAsArrayBuffer(file);
  }.toJS;

  input.click();
  return completer.future;
}
