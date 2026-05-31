import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';
import '../../assets/data/assets_repository.dart';

class TaxonomyRepository {
  TaxonomyRepository(this._api);
  final ApiClient _api;

  Future<List<TagNode>> listTags({
    bool albums = false,
    int? parentId,
    int? subtreeId,
  }) => _api.getJson(
    albums ? '/albums/' : '/tags/',
    (json) => (json as List)
        .whereType<Map>()
        .map((e) => TagNode.fromJson(e.cast<String, dynamic>()))
        .toList(),
    query: {'parent_id': parentId, 'subtree_id': subtreeId},
  );

  Future<TagNode> create({
    required bool album,
    required String name,
    int? parentId,
    String? description,
  }) => _api.postJson(
    album ? '/albums/' : '/tags/',
    {
      'name': name,
      if (parentId != null) 'parent_id': parentId,
      if (description != null) 'description': description,
    },
    (json) => TagNode.fromJson((json as Map).cast<String, dynamic>()),
  );

  Future<TagNode> update({
    required bool album,
    required int id,
    String? name,
    int? parentId,
    String? description,
    String? coverAssetId,
  }) => _api.patchJson(
    '${album ? '/albums' : '/tags'}/$id',
    {
      if (name != null) 'name': name,
      if (parentId != null) 'parent_id': parentId,
      if (description != null) 'description': description,
      if (coverAssetId != null) 'cover_asset_id': coverAssetId,
    },
    (json) => TagNode.fromJson((json as Map).cast<String, dynamic>()),
  );

  Future<void> deleteTag({
    required bool album,
    required int id,
    bool deleteChildren = false,
  }) => _api.delete(
    '${album ? '/albums' : '/tags'}/$id',
    query: {'delete_children': deleteChildren},
  );

  Future<PagedAssetsState> assets({
    required bool album,
    required int id,
    String? cursor,
  }) async {
    final page = await _api.getJson(
      '${album ? '/albums' : '/tags'}/$id/assets',
      (json) => AssetGridPage.fromJson((json as Map).cast<String, dynamic>()),
      query: {'limit': 100, 'cursor': cursor},
    );
    return PagedAssetsState(
      items: page.items,
      nextCursor: page.nextCursor,
      hasMore: page.hasMore,
    );
  }
}
