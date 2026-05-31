import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class SearchRepository {
  SearchRepository(this._api);
  final ApiClient _api;

  Future<AssetGridPage> search({
    String? query,
    List<String> personIds = const [],
    List<int> tagIds = const [],
    String? cursor,
  }) => _api.getJson(
    '/search/',
    (json) {
      final map = (json as Map).cast<String, dynamic>();
      return AssetGridPage(
        items: asMapList(map['items']).map(AssetGridItem.fromJson).toList(),
        hasMore: map['has_more'] as bool? ?? false,
        nextCursor: map['next_cursor'] as String?,
      );
    },
    query: {
      'query': query,
      'person_ids': personIds,
      'tag_ids': tagIds,
      'cursor': cursor,
      'limit': 50,
    },
  );
}
