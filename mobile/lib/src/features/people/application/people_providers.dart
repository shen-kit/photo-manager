import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../../faces/data/faces_repository.dart';
import '../data/people_repository.dart';

final peopleRepositoryProvider = Provider<PeopleRepository>(
  (ref) => PeopleRepository(ref.watch(apiClientProvider)),
);
final facesRepositoryProvider = Provider<FacesRepository>(
  (ref) => FacesRepository(ref.watch(apiClientProvider)),
);
final peopleProvider = FutureProvider<List<Person>>(
  (ref) => ref.watch(peopleRepositoryProvider).list(),
);
