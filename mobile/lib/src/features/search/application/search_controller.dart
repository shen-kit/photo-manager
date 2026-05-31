import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/config/app_settings.dart';
import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../data/search_repository.dart';

final searchRepositoryProvider = Provider<SearchRepository>(
  (ref) => SearchRepository(ref.watch(apiClientProvider)),
);

final searchControllerProvider =
    StateNotifierProvider<SearchController, AsyncValue<List<AssetGridItem>>>(
      (ref) => SearchController(
        ref.watch(searchRepositoryProvider),
        ref.watch(appSettingsProvider),
      ),
    );

class SearchController extends StateNotifier<AsyncValue<List<AssetGridItem>>> {
  SearchController(this._repo, this._settings) : super(const AsyncData([]));
  final SearchRepository _repo;
  final AppSettingsStore _settings;
  Timer? _timer;
  SearchStateData filters = const SearchStateData();
  String? _cursor;
  bool _hasMore = false;

  bool get hasMore => _hasMore;

  void update(SearchStateData next) {
    filters = next;
    _timer?.cancel();
    _timer = Timer(
      const Duration(milliseconds: 350),
      () => search(reset: true),
    );
  }

  Future<void> search({bool reset = false}) async {
    if (reset) {
      _cursor = null;
      _hasMore = false;
    }
    final active =
        filters.query.trim().isNotEmpty ||
        filters.personIds.isNotEmpty ||
        filters.tagIds.isNotEmpty;
    if (!active) {
      state = const AsyncData([]);
      return;
    }
    if (reset) state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final page = await _repo.search(
        query: filters.query,
        personIds: filters.personIds,
        tagIds: filters.tagIds,
        cursor: _cursor,
      );
      _cursor = page.nextCursor;
      _hasMore = page.hasMore;
      if (filters.query.trim().isNotEmpty)
        await _settings.addRecentSearch(filters.query);
      return reset ? page.items : [...?state.valueOrNull, ...page.items];
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
