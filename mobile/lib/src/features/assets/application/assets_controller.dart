import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers.dart';
import '../data/assets_repository.dart';

final assetsRepositoryProvider = Provider<AssetsRepository>(
  (ref) => AssetsRepository(ref.watch(apiClientProvider)),
);

final assetFilterProvider = StateProvider<AssetFilter>(
  (ref) => const AssetFilter(),
);

final assetsControllerProvider =
    StateNotifierProvider<AssetsController, AsyncValue<PagedAssetsState>>((
      ref,
    ) {
      final filter = ref.watch(assetFilterProvider);
      return AssetsController(ref.watch(assetsRepositoryProvider), filter)
        ..load();
    });

class AssetsController extends StateNotifier<AsyncValue<PagedAssetsState>> {
  AssetsController(this._repo, this.filter) : super(const AsyncLoading());
  final AssetsRepository _repo;
  final AssetFilter filter;

  Future<void> load({bool force = false}) async {
    final cached = _repo.cached(filter);
    if (!force && cached != null) state = AsyncData(cached);
    state = await AsyncValue.guard(() => _repo.firstPage(filter, force: force));
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || !current.hasMore || current.isLoadingMore) return;
    state = AsyncData(current.copyWith(isLoadingMore: true));
    state = await AsyncValue.guard(() => _repo.nextPage(filter));
  }

  Future<void> deleteAsset(String id) async {
    await _repo.softDelete(id);
    await load(force: false);
  }
}
