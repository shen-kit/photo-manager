import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../../assets/application/assets_controller.dart';
import '../data/local_media_repository.dart';

final localMediaRepositoryProvider = Provider<LocalMediaRepository>(
  (ref) => LocalMediaRepository(
    ref.watch(appSettingsProvider),
    ref.watch(assetsRepositoryProvider),
  ),
);
final backupSourcesProvider = FutureProvider<List<BackupSource>>(
  (ref) => ref.watch(localMediaRepositoryProvider).discoverSources(),
);
final localIndexProvider = FutureProvider<List<LocalMediaItem>>(
  (ref) async => ref.watch(localMediaRepositoryProvider).index,
);
