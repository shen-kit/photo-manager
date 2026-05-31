import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:mime/mime.dart';

import '../config/app_settings.dart';
import '../models/models.dart';
import '../storage/session_store.dart';
import '../utils/app_logger.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode, this.details});
  final String message;
  final int? statusCode;
  final Object? details;

  bool get isUnauthorized => statusCode == 401;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({
    required AppSettingsStore settings,
    required SessionStore sessionStore,
    http.Client? httpClient,
  }) : _settings = settings,
       _sessionStore = sessionStore,
       _http = httpClient ?? http.Client();

  final AppSettingsStore _settings;
  final SessionStore _sessionStore;
  final http.Client _http;
  String? _lastRefreshCookie;

  String? get lastRefreshCookie => _lastRefreshCookie;

  Uri apiUri(String path, [Map<String, Object?> query = const {}]) {
    final base = Uri.parse(_settings.baseUrl);
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    final prefix = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    return base.replace(
      path: '$prefix/api/v1$normalizedPath',
      queryParameters: _query(query),
    );
  }

  Uri mediaUri(String urlOrPath) {
    final uri = Uri.tryParse(urlOrPath);
    if (uri != null && uri.hasScheme) return uri;
    final base = Uri.parse(_settings.baseUrl);
    return base.replace(
      path: urlOrPath.startsWith('/') ? urlOrPath : '/$urlOrPath',
    );
  }

  Future<Map<String, String>> authImageHeaders() async {
    final session = await _sessionStore.read();
    return {
      if (session?.accessToken case final token?)
        'Authorization': 'Bearer $token',
      if (session?.refreshCookie case final cookie?) 'Cookie': cookie,
    };
  }

  Future<T> getJson<T>(
    String path,
    T Function(Object json) decode, {
    Map<String, Object?> query = const {},
  }) => _sendJson('GET', path, decode, query: query);

  Future<T> postJson<T>(
    String path,
    Object? body,
    T Function(Object json) decode, {
    Map<String, Object?> query = const {},
  }) => _sendJson('POST', path, decode, query: query, body: body);

  Future<T> patchJson<T>(
    String path,
    Object? body,
    T Function(Object json) decode, {
    Map<String, Object?> query = const {},
  }) => _sendJson('PATCH', path, decode, query: query, body: body);

  Future<void> delete(
    String path, {
    Map<String, Object?> query = const {},
  }) async {
    await _sendJson<Object?>('DELETE', path, (_) => null, query: query);
  }

  Future<T> uploadFile<T>(
    String path,
    File file,
    T Function(Object json) decode,
  ) async {
    final request = http.MultipartRequest('POST', apiUri(path));
    await _attachAuth(request.headers);
    final mime = lookupMimeType(file.path) ?? 'application/octet-stream';
    request.files.add(
      await http.MultipartFile.fromPath(
        'file',
        file.path,
        contentType: MediaType.parse(mime),
      ),
    );
    final streamed = await request.send().timeout(const Duration(minutes: 5));
    final response = await http.Response.fromStream(streamed);
    _captureRefreshCookie(response);
    if (response.statusCode == 401 && await _refresh()) {
      final retry = http.MultipartRequest('POST', apiUri(path));
      await _attachAuth(retry.headers);
      retry.files.add(
        await http.MultipartFile.fromPath(
          'file',
          file.path,
          contentType: MediaType.parse(mime),
        ),
      );
      final retryResponse = await http.Response.fromStream(
        await retry.send().timeout(const Duration(minutes: 5)),
      );
      return _decodeResponse(retryResponse, decode);
    }
    return _decodeResponse(response, decode);
  }

  Future<T> _sendJson<T>(
    String method,
    String path,
    T Function(Object json) decode, {
    Map<String, Object?> query = const {},
    Object? body,
    bool allowRefresh = true,
  }) async {
    final request = http.Request(method, apiUri(path, query));
    request.headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    await _attachAuth(request.headers);

    try {
      final response = await http.Response.fromStream(
        await _http.send(request).timeout(const Duration(seconds: 30)),
      );
      _captureRefreshCookie(response);
      if (response.statusCode == 401 &&
          allowRefresh &&
          !path.startsWith('/auth/refresh') &&
          await _refresh()) {
        return _sendJson(
          method,
          path,
          decode,
          query: query,
          body: body,
          allowRefresh: false,
        );
      }
      return _decodeResponse(response, decode);
    } on TimeoutException catch (error) {
      throw ApiException('Request timed out', details: error);
    } on SocketException catch (error) {
      throw ApiException('Network unavailable', details: error);
    }
  }

  T _decodeResponse<T>(http.Response response, T Function(Object json) decode) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final body = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      return decode(body);
    }
    Object? details;
    String message = 'Request failed (${response.statusCode})';
    if (response.body.isNotEmpty) {
      try {
        details = jsonDecode(response.body);
        if (details case {'detail': final detail}) message = detail.toString();
      } catch (_) {
        details = response.body;
      }
    }
    throw ApiException(
      message,
      statusCode: response.statusCode,
      details: details,
    );
  }

  Future<void> _attachAuth(Map<String, String> headers) async {
    final session = await _sessionStore.read();
    if (session == null) return;
    headers['Authorization'] = 'Bearer ${session.accessToken}';
    if (session.refreshCookie != null)
      headers['Cookie'] = session.refreshCookie!;
  }

  void _captureRefreshCookie(http.Response response) {
    final setCookie = response.headers['set-cookie'];
    if (setCookie == null || setCookie.isEmpty) return;
    final cookie = setCookie.split(';').first;
    if (!cookie.contains('=')) return;
    _lastRefreshCookie = cookie;
    _sessionStore.read().then((session) {
      if (session != null)
        _sessionStore.write(session.copyWith(refreshCookie: cookie));
    });
  }

  Future<bool> _refresh() async {
    final session = await _sessionStore.read();
    if (session?.refreshCookie == null) return false;
    try {
      final auth = await _sendJson<AuthResponse>(
        'POST',
        '/auth/refresh',
        (json) => AuthResponse.fromJson((json as Map).cast<String, dynamic>()),
        allowRefresh: false,
      );
      await _sessionStore.write(
        SessionData.fromAuth(auth, refreshCookie: session!.refreshCookie),
      );
      return true;
    } catch (error) {
      appLogger.debug('Refresh failed', error: error);
      await _sessionStore.clear();
      return false;
    }
  }

  Map<String, String>? _query(Map<String, Object?> query) {
    final values = <String, String>{};
    for (final entry in query.entries) {
      final value = entry.value;
      if (value == null) continue;
      if (value is Iterable) {
        if (value.isEmpty) continue;
        values[entry.key] = value.join(',');
      } else {
        values[entry.key] = value.toString();
      }
    }
    return values.isEmpty ? null : values;
  }
}
