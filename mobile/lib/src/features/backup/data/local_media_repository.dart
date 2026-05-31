import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:photo_manager/photo_manager.dart' as pm;

import '../../../shared/config/app_settings.dart';
import '../../../shared/models/models.dart';
import '../../assets/data/assets_repository.dart';

class LocalMediaRepository {
  LocalMediaRepository(this._settings, this._assetsRepository);
  final AppSettingsStore _settings;
  final AssetsRepository _assetsRepository;

  List<LocalMediaItem> get index => _settings.localIndex;

  Future<bool> requestPermission() async {
    final permission = await pm.PhotoManager.requestPermissionExtend();
    return permission.isAuth || permission.hasAccess;
  }

  Future<List<BackupSource>> discoverSources() async {
    final granted = await requestPermission();
    if (!granted) return const [];
    final paths = await pm.PhotoManager.getAssetPathList(
      type: pm.RequestType.common,
      filterOption: pm.FilterOptionGroup(),
    );
    final selected = _settings.selectedBackupSourceIds;
    final sources = <BackupSource>[];
    for (final p in paths) {
      sources.add(
        BackupSource(
          id: p.id,
          name: p.name,
          assetCount: await p.assetCountAsync,
          selected: selected.contains(p.id),
        ),
      );
    }
    return sources;
  }

  Future<void> setSourceSelected(String id, bool selected) async {
    final ids = {..._settings.selectedBackupSourceIds};
    selected ? ids.add(id) : ids.remove(id);
    await _settings.setSelectedBackupSourceIds(ids);
  }

  Future<List<LocalMediaItem>> scanSelectedSources() async {
    final granted = await requestPermission();
    if (!granted) return index;
    final selected = _settings.selectedBackupSourceIds;
    if (selected.isEmpty) {
      await _settings.setLocalIndex(const []);
      return const [];
    }
    final paths = await pm.PhotoManager.getAssetPathList(
      type: pm.RequestType.common,
    );
    final found = <LocalMediaItem>[];
    for (final path in paths.where((p) => selected.contains(p.id))) {
      final count = await path.assetCountAsync;
      final assets = await path.getAssetListRange(start: 0, end: count);
      for (final asset in assets) {
        final file = await asset.file;
        found.add(
          LocalMediaItem(
            id: asset.id,
            uri: file?.path ?? asset.id,
            filename: asset.title ?? asset.id,
            mediaKind: asset.type == pm.AssetType.video ? 'video' : 'image',
            bucketId: path.id,
            bucketName: path.name,
            sizeBytes: file == null ? null : await file.length(),
            createdAt: asset.createDateTime,
            modifiedAt: asset.modifiedDateTime,
            mimeType: asset.mimeType,
            isAvailable: file != null && await file.exists(),
          ),
        );
      }
    }
    await _settings.setLocalIndex(found);
    return found;
  }

  Future<File?> resolveLocalFile(AssetDetail asset) async {
    final match = LocalAssetResolver(index).resolve(asset);
    if (match == null) return null;
    final file = File(match.uri);
    return await file.exists() ? file : null;
  }

  Future<LocalMediaItem> hashItem(LocalMediaItem item) async {
    final file = File(item.uri);
    if (!await file.exists()) return item.copyWith(isAvailable: false);
    final digest = await sha256.bind(file.openRead()).first;
    return item.copyWith(sha256: digest.toString());
  }

  Future<List<LocalMediaItem>> uploadPending() async {
    final items = [...index];
    for (var i = 0; i < items.length; i++) {
      final item = items[i];
      if (!item.isAvailable ||
          item.matchedAssetId != null ||
          item.uploadState == UploadState.uploading ||
          item.uploadState == UploadState.uploaded)
        continue;
      final file = File(item.uri);
      if (!await file.exists()) {
        items[i] = item.copyWith(
          isAvailable: false,
          uploadState: UploadState.failed,
          lastError: 'Local file unavailable',
        );
        continue;
      }
      items[i] = item.copyWith(
        uploadState: UploadState.uploading,
        lastError: null,
      );
      await _settings.setLocalIndex(items);
      try {
        final uploaded = await _assetsRepository.upload(file);
        items[i] = item.copyWith(
          uploadState: UploadState.uploaded,
          matchedAssetId: uploaded.id,
          sha256: uploaded.fileHash,
          lastError: null,
        );
      } catch (error) {
        items[i] = item.copyWith(
          uploadState: UploadState.failed,
          lastError: error.toString(),
          retryCount: item.retryCount + 1,
        );
      }
      await _settings.setLocalIndex(items);
    }
    return items;
  }
}

class LocalAssetResolver {
  const LocalAssetResolver(this.index);
  final List<LocalMediaItem> index;

  LocalMediaItem? resolve(AssetDetail asset) {
    final available = index.where((i) => i.isAvailable).toList();
    final hashMatches = available
        .where((i) => i.sha256 != null && i.sha256 == asset.fileHash)
        .toList();
    if (hashMatches.length == 1) return hashMatches.single;
    final basename = asset.masterPath.split('/').last.toLowerCase();
    final strong = available.where((i) {
      final nameMatch =
          i.filename.toLowerCase() == basename ||
          basename.endsWith(i.filename.toLowerCase());
      final sizeMatch =
          asset.fileSizeBytes != null && i.sizeBytes == asset.fileSizeBytes;
      final kindMatch =
          i.mediaKind == asset.mediaKind ||
          asset.mimeType.startsWith(i.mediaKind);
      final timeMatch =
          _closeEnough(i.createdAt, asset.capturedAt) ||
          _closeEnough(i.modifiedAt, asset.capturedAt);
      return kindMatch &&
          ((nameMatch && sizeMatch) ||
              (sizeMatch && timeMatch) ||
              (nameMatch && timeMatch));
    }).toList();
    return strong.length == 1 ? strong.single : null;
  }

  bool _closeEnough(DateTime? left, DateTime? right) {
    if (left == null || right == null) return false;
    return left.difference(right).abs() <= const Duration(minutes: 2);
  }
}

String safeLocalIndexDebug(List<LocalMediaItem> items) => jsonEncode(
  items
      .map(
        (e) => {
          'id': e.id,
          'filename': e.filename,
          'state': e.uploadState.name,
        },
      )
      .toList(),
);
