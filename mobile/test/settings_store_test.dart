import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager_mobile/src/shared/config/app_settings.dart';
import 'package:photo_manager_mobile/src/shared/models/models.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('backup sources default empty and persist', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final store = AppSettingsStore(prefs);
    expect(store.selectedBackupSourceIds, isEmpty);
    await store.setSelectedBackupSourceIds({'camera'});
    expect(store.selectedBackupSourceIds, {'camera'});
  });

  test('local index round trips upload state', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final store = AppSettingsStore(prefs);
    const item = LocalMediaItem(
      id: '1',
      uri: '/tmp/a.jpg',
      filename: 'a.jpg',
      mediaKind: 'image',
      uploadState: UploadState.failed,
      retryCount: 2,
    );
    await store.setLocalIndex([item]);
    expect(store.localIndex.single.uploadState, UploadState.failed);
    expect(store.localIndex.single.retryCount, 2);
  });
}
