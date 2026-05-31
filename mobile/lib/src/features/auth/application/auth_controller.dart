import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers.dart';
import '../../../shared/storage/session_store.dart';
import '../data/auth_repository.dart';

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(sessionStoreProvider),
  ),
);

final authControllerProvider =
    StateNotifierProvider<AuthController, AsyncValue<SessionData?>>(
      (ref) => AuthController(ref.watch(authRepositoryProvider))..restore(),
    );

class AuthController extends StateNotifier<AsyncValue<SessionData?>> {
  AuthController(this._repository) : super(const AsyncLoading());
  final AuthRepository _repository;

  Future<void> restore() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_repository.restore);
  }

  Future<void> login(String username, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => _repository.login(username: username, password: password),
    );
  }

  Future<void> logout() async {
    await _repository.logout();
    state = const AsyncData(null);
  }
}
