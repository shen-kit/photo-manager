import 'dart:io';

import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class AssetFilter {
  const AssetFilter({
    this.mediaKind,
    this.month,
    this.day,
    this.personIds = const [],
    this.tagIds = const [],
  });
  final String? mediaKind;
  final String? month;
  final String? day;
  final List<String> personIds;
  final List<int> tagIds;

  String get key =>
      [mediaKind, month, day, personIds.join(','), tagIds.join(',')].join('|');
  Map<String, Object?> toQuery({int limit = 100, String? cursor}) => {
    'limit': limit,
    'cursor': cursor,
    'media_kind': mediaKind,
    'month': month,
    'day': day,
    'person_ids': personIds,
    'tag_ids': tagIds,
  };
}

class PagedAssetsState {
  const PagedAssetsState({
    this.items = const [],
    this.nextCursor,
    this.hasMore = true,
    this.isLoadingMore = false,
  });
  final List<AssetGridItem> items;
  final String? nextCursor;
  final bool hasMore;
  final bool isLoadingMore;

  PagedAssetsState copyWith({
    List<AssetGridItem>? items,
    String? nextCursor,
    bool? hasMore,
    bool? isLoadingMore,
  }) => PagedAssetsState(
    items: items ?? this.items,
    nextCursor: nextCursor ?? this.nextCursor,
    hasMore: hasMore ?? this.hasMore,
    isLoadingMore: isLoadingMore ?? this.isLoadingMore,
  );
}

class AssetsRepository {
  AssetsRepository(this._api);
  final ApiClient _api;
  final Map<String, PagedAssetsState> _pageCache = {};
  final Map<String, AssetDetail> _detailCache = {};

  PagedAssetsState? cached(AssetFilter filter) => _pageCache[filter.key];
  void clearCache() => _pageCache.clear();

  Future<PagedAssetsState> firstPage(
    AssetFilter filter, {
    bool force = false,
  }) async {
    if (!force && _pageCache[filter.key] != null)
      return _pageCache[filter.key]!;
    final page = await _fetch(filter, cursor: null);
    final state = PagedAssetsState(
      items: page.items,
      nextCursor: page.nextCursor,
      hasMore: page.hasMore,
    );
    _pageCache[filter.key] = state;
    return state;
  }

  Future<PagedAssetsState> nextPage(AssetFilter filter) async {
    final current = _pageCache[filter.key] ?? const PagedAssetsState();
    if (!current.hasMore || current.isLoadingMore) return current;
    _pageCache[filter.key] = current.copyWith(isLoadingMore: true);
    final page = await _fetch(filter, cursor: current.nextCursor);
    final state = PagedAssetsState(
      items: [...current.items, ...page.items],
      nextCursor: page.nextCursor,
      hasMore: page.hasMore,
    );
    _pageCache[filter.key] = state;
    return state;
  }

  Future<AssetGridPage> _fetch(AssetFilter filter, {String? cursor}) =>
      _api.getJson(
        '/assets/',
        (json) => AssetGridPage.fromJson((json as Map).cast<String, dynamic>()),
        query: filter.toQuery(cursor: cursor),
      );

  Future<AssetDetail> detail(String id, {bool force = false}) async {
    if (!force && _detailCache[id] != null) return _detailCache[id]!;
    final detail = await _api.getJson(
      '/assets/$id',
      (json) => AssetDetail.fromJson((json as Map).cast<String, dynamic>()),
    );
    _detailCache[id] = detail;
    return detail;
  }

  Future<AssetDetail> update(
    String id, {
    DateTime? capturedAt,
    bool? isFavorite,
    String? description,
  }) async {
    final body = {
      if (capturedAt != null)
        'captured_at': capturedAt.toUtc().toIso8601String(),
      if (isFavorite != null) 'is_favorite': isFavorite,
      if (description != null) 'description': description,
    };
    final detail = await _api.patchJson(
      '/assets/$id',
      body,
      (json) => AssetDetail.fromJson((json as Map).cast<String, dynamic>()),
    );
    _detailCache[id] = detail;
    return detail;
  }

  Future<void> softDelete(String id) async {
    await _api.delete('/assets/$id');
    _detailCache.remove(id);
    for (final entry in _pageCache.entries.toList()) {
      _pageCache[entry.key] = entry.value.copyWith(
        items: entry.value.items.where((a) => a.id != id).toList(),
      );
    }
  }

  Future<List<TimelineMonth>> months(AssetFilter filter) => _api.getJson(
    '/timeline/months',
    (json) => (json as List)
        .whereType<Map>()
        .map((e) => TimelineMonth.fromJson(e.cast<String, dynamic>()))
        .toList(),
    query: {
      'media_kind': filter.mediaKind,
      'person_ids': filter.personIds,
      'tag_ids': filter.tagIds,
    },
  );

  Future<List<AssetPreviewEnsureItem>> ensurePreviews(
    List<String> ids, {
    String priority = 'low',
  }) => _api.postJson(
    '/assets/previews/ensure',
    {'asset_ids': ids, 'priority': priority},
    (json) => asMapList(
      (json as Map)['items'],
    ).map(AssetPreviewEnsureItem.fromJson).toList(),
  );

  Future<void> addTag(String assetId, int tagId) =>
      _api.postJson('/assets/$assetId/tags/$tagId', null, (_) => null);
  Future<void> removeTag(String assetId, int tagId) =>
      _api.delete('/assets/$assetId/tags/$tagId');
  Future<int> batchAddTags(List<String> assetIds, List<int> tagIds) =>
      _api.postJson('/assets/tags:batch-add', {
        'asset_ids': assetIds,
        'tag_ids': tagIds,
      }, (json) => (json as Map)['updated_count'] as int? ?? 0);
  Future<int> batchRemoveTags(List<String> assetIds, List<int> tagIds) =>
      _api.postJson(
        '/assets/tags:batch-remove',
        {'asset_ids': assetIds, 'tag_ids': tagIds},
        (json) => (json as Map)['updated_count'] as int? ?? 0,
      );
  Future<AssetDetail> upload(File file) => _api.uploadFile(
    '/assets/upload',
    file,
    (json) => AssetDetail.fromJson((json as Map).cast<String, dynamic>()),
  );
}
