import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager_mobile/src/shared/models/models.dart';

void main() {
  test('auth response parses user', () {
    final auth = AuthResponse.fromJson({
      'access_token': 'token',
      'expires_in': 900,
      'user': {'id': 'u1', 'username': 'testuser', 'is_active': true},
    });
    expect(auth.user.username, 'testuser');
  });

  test('tag path depth and album flag parse', () {
    final tag = TagNode.fromJson({
      'id': 1,
      'name': 'China',
      'slug': 'china',
      'path': 'holidays.china',
      'is_album': true,
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
    });
    expect(tag.path.split('.'), ['holidays', 'china']);
    expect(tag.isAlbum, isTrue);
  });

  test('search filter state keeps AND tag set', () {
    const state = SearchStateData(
      query: 'beach',
      personIds: ['p1'],
      tagIds: [1, 2],
    );
    expect(state.tagIds, [1, 2]);
  });
}
