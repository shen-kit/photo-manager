import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/models.dart';

class SessionData {
  const SessionData({
    required this.accessToken,
    required this.user,
    this.refreshCookie,
    this.expiresAt,
  });
  final String accessToken;
  final String? refreshCookie;
  final DateTime? expiresAt;
  final User user;

  SessionData copyWith({
    String? accessToken,
    String? refreshCookie,
    DateTime? expiresAt,
    User? user,
  }) => SessionData(
    accessToken: accessToken ?? this.accessToken,
    refreshCookie: refreshCookie ?? this.refreshCookie,
    expiresAt: expiresAt ?? this.expiresAt,
    user: user ?? this.user,
  );

  Map<String, dynamic> toJson() => {
    'access_token': accessToken,
    'refresh_cookie': refreshCookie,
    'expires_at': dateString(expiresAt),
    'user': user.toJson(),
  };

  factory SessionData.fromAuth(AuthResponse auth, {String? refreshCookie}) =>
      SessionData(
        accessToken: auth.accessToken,
        refreshCookie: refreshCookie,
        expiresAt: DateTime.now().add(Duration(seconds: auth.expiresIn)),
        user: auth.user,
      );

  factory SessionData.fromJson(Map<String, dynamic> json) => SessionData(
    accessToken: json['access_token'] as String,
    refreshCookie: json['refresh_cookie'] as String?,
    expiresAt: parseDateTime(json['expires_at']),
    user: User.fromJson((json['user'] as Map).cast<String, dynamic>()),
  );
}

class SessionStore {
  SessionStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();
  static const _sessionKey = 'photo_manager_session';
  final FlutterSecureStorage _storage;

  SessionData? _memory;

  Future<SessionData?> read() async {
    if (_memory != null) return _memory;
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null) return null;
    try {
      _memory = SessionData.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      return _memory;
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> write(SessionData data) async {
    _memory = data;
    await _storage.write(key: _sessionKey, value: jsonEncode(data.toJson()));
  }

  Future<void> clear() async {
    _memory = null;
    await _storage.delete(key: _sessionKey);
  }
}
