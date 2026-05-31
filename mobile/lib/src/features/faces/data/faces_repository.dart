import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class FacesRepository {
  FacesRepository(this._api);
  final ApiClient _api;

  Future<List<AssetFace>> listForAsset(String assetId) => _api.getJson(
    '/assets/$assetId/faces',
    (json) => (json as List)
        .whereType<Map>()
        .map((e) => AssetFace.fromJson(e.cast<String, dynamic>()))
        .toList(),
  );
  Future<AssetFace> patch(
    String faceId, {
    bool? isConfirmed,
    bool? isExcluded,
    String? personId,
  }) => _api.patchJson(
    '/faces/$faceId',
    {
      if (isConfirmed != null) 'is_confirmed': isConfirmed,
      if (isExcluded != null) 'is_excluded': isExcluded,
      if (personId != null) 'person_id': personId,
    },
    (json) => AssetFace.fromJson((json as Map).cast<String, dynamic>()),
  );
  Future<JobRead> process(
    String assetId, {
    bool force = false,
    bool autoMatch = true,
  }) => _api.postJson(
    '/assets/$assetId/faces/process',
    null,
    (json) => JobRead.fromJson((json as Map).cast<String, dynamic>()),
    query: {'force': force, 'auto_match': autoMatch},
  );
  Future<void> match(String assetId) =>
      _api.postJson('/assets/$assetId/faces/match', null, (_) => null);
}
