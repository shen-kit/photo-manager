import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../data/trash_repository.dart';

final trashRepositoryProvider = Provider<TrashRepository>(
  (ref) => TrashRepository(ref.watch(apiClientProvider)),
);
final trashProvider = FutureProvider<TrashPage>(
  (ref) => ref.watch(trashRepositoryProvider).list(),
);
