import 'package:flutter/foundation.dart';

class AppLogger {
  const AppLogger();

  void debug(String message, {Object? error}) {
    if (!kDebugMode) return;
    final safe = _redact(message);
    debugPrint(error == null ? safe : '$safe: ${_redact(error.toString())}');
  }

  String _redact(String input) {
    var output = input;
    output = output.replaceAll(
      RegExp(r'Bearer\s+[A-Za-z0-9._\-]+'),
      'Bearer <redacted>',
    );
    output = output.replaceAll(
      RegExp(
        r'(access_token|refresh_token|password|cookie)=?[^\s,}]+',
        caseSensitive: false,
      ),
      r'$1=<redacted>',
    );
    output = output.replaceAll(RegExp(r'(/[\w .-]+){3,}'), '<path-redacted>');
    return output;
  }
}

const appLogger = AppLogger();
