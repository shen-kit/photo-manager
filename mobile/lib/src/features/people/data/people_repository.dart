import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class PeopleRepository {
  PeopleRepository(this._api);
  final ApiClient _api;

  Future<List<Person>> list({bool includeHidden = false, String? search}) =>
      _api.getJson(
        '/people/',
        (json) => (json as List)
            .whereType<Map>()
            .map((e) => Person.fromJson(e.cast<String, dynamic>()))
            .toList(),
        query: {'include_hidden': includeHidden, 'search': search},
      );
  Future<Person> update(
    String id, {
    String? name,
    bool? isHidden,
    String? thumbnailFaceId,
  }) => _api.patchJson('/people/$id', {
    if (name != null) 'name': name,
    if (isHidden != null) 'is_hidden': isHidden,
    if (thumbnailFaceId != null) 'thumbnail_face_id': thumbnailFaceId,
  }, (json) => Person.fromJson((json as Map).cast<String, dynamic>()));
  Future<Person> setThumbnail(String id, String assetId) => _api.patchJson(
    '/people/$id/thumbnail',
    {'asset_id': assetId},
    (json) => Person.fromJson((json as Map).cast<String, dynamic>()),
  );
  Future<void> merge(String sourceId, String targetId) => _api.postJson(
    '/people/$sourceId/merge-into/$targetId',
    null,
    (_) => null,
  );
}
