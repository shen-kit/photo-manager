import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class TrashRepository {
  TrashRepository(this._api);
  final ApiClient _api;

  Future<TrashPage> list({
    int page = 1,
    int pageSize = 100,
    String sort = 'deleted_at_desc',
  }) => _api.getJson(
    '/trash/assets/',
    (json) => TrashPage.fromJson((json as Map).cast<String, dynamic>()),
    query: {'page': page, 'page_size': pageSize, 'sort': sort},
  );
  Future<AssetDetail> detail(String id) => _api.getJson(
    '/trash/assets/$id',
    (json) => AssetDetail.fromJson((json as Map).cast<String, dynamic>()),
  );
  Future<void> restore(String id) =>
      _api.postJson('/trash/assets/$id/restore', null, (_) => null);
  Future<void> bulkRestore(List<String> ids) =>
      _api.postJson('/trash/assets/restore', {'asset_ids': ids}, (_) => null);
  Future<void> deletePermanent(String id) => _api.delete('/trash/assets/$id');
  Future<void> bulkDelete(List<String> ids) =>
      _api.postJson('/trash/assets/delete', {'asset_ids': ids}, (_) => null);
  Future<void> empty() => _api.delete('/trash/assets/');
}
