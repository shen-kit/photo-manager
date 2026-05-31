import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager_mobile/src/features/backup/data/local_media_repository.dart';
import 'package:photo_manager_mobile/src/shared/models/models.dart';

void main() {
  test('hash match wins local resolution', () {
    final asset = _asset(fileHash: 'abc');
    final local = LocalMediaItem(
      id: '1',
      uri: '/tmp/a.jpg',
      filename: 'a.jpg',
      mediaKind: 'image',
      sha256: 'abc',
    );
    expect(LocalAssetResolver([local]).resolve(asset), local);
  });

  test('ambiguous weak matches return null', () {
    final asset = _asset(
      fileSizeBytes: 10,
      masterPath: '2026/a.jpg',
      capturedAt: DateTime(2026),
    );
    final locals = [
      LocalMediaItem(
        id: '1',
        uri: '/tmp/a.jpg',
        filename: 'a.jpg',
        mediaKind: 'image',
        sizeBytes: 10,
        createdAt: DateTime(2026),
      ),
      LocalMediaItem(
        id: '2',
        uri: '/tmp/a2.jpg',
        filename: 'a.jpg',
        mediaKind: 'image',
        sizeBytes: 10,
        createdAt: DateTime(2026),
      ),
    ];
    expect(LocalAssetResolver(locals).resolve(asset), isNull);
  });
}

AssetDetail _asset({
  String fileHash = 'hash',
  String masterPath = 'a.jpg',
  int? fileSizeBytes,
  DateTime? capturedAt,
}) => AssetDetail(
  id: 'asset',
  fileHash: fileHash,
  masterPath: masterPath,
  mimeType: 'image/jpeg',
  mediaKind: 'image',
  timelineDay: '2026-01-01',
  capturedAt: capturedAt,
  isFavorite: false,
  hasLargePreview: false,
  smallThumbnailUrl: '/small.webp',
  previewUrl: '/large.webp',
  createdAt: DateTime(2026),
  fileSizeBytes: fileSizeBytes,
);
