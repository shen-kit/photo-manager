import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../data/taxonomy_repository.dart';

final taxonomyRepositoryProvider = Provider<TaxonomyRepository>(
  (ref) => TaxonomyRepository(ref.watch(apiClientProvider)),
);
final tagsProvider = FutureProvider<List<TagNode>>(
  (ref) => ref.watch(taxonomyRepositoryProvider).listTags(),
);
final albumsProvider = FutureProvider<List<TagNode>>(
  (ref) => ref.watch(taxonomyRepositoryProvider).listTags(albums: true),
);
