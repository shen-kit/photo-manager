import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';
import '../../../shared/storage/session_store.dart';

class AuthRepository {
  AuthRepository(this._api, this._sessionStore);
  final ApiClient _api;
  final SessionStore _sessionStore;

  Future<SessionData?> restore() => _sessionStore.read();

  Future<SessionData> login({
    required String username,
    required String password,
  }) async {
    final auth = await _api.postJson(
      '/auth/login',
      {'username': username, 'password': password},
      (json) => AuthResponse.fromJson((json as Map).cast<String, dynamic>()),
    );
    final current = await _sessionStore.read();
    final session = SessionData.fromAuth(
      auth,
      refreshCookie: _api.lastRefreshCookie ?? current?.refreshCookie,
    );
    await _sessionStore.write(session);
    return session;
  }

  Future<SessionData> register({
    required String username,
    required String password,
  }) async {
    final auth = await _api.postJson(
      '/auth/register',
      {'username': username, 'password': password},
      (json) => AuthResponse.fromJson((json as Map).cast<String, dynamic>()),
    );
    final current = await _sessionStore.read();
    final session = SessionData.fromAuth(
      auth,
      refreshCookie: _api.lastRefreshCookie ?? current?.refreshCookie,
    );
    await _sessionStore.write(session);
    return session;
  }

  Future<User> me() => _api.getJson(
    '/auth/me',
    (json) => User.fromJson((json as Map).cast<String, dynamic>()),
  );

  Future<void> logout() async {
    try {
      await _api.postJson('/auth/logout', null, (_) => null);
    } finally {
      await _sessionStore.clear();
    }
  }
}
