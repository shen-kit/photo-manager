import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../data/operations_repository.dart';

final operationsRepositoryProvider = Provider<OperationsRepository>(
  (ref) => OperationsRepository(ref.watch(apiClientProvider)),
);
final jobsProvider = FutureProvider<List<JobRead>>(
  (ref) => ref.watch(operationsRepositoryProvider).jobs(),
);
final manualJobsProvider = FutureProvider<List<ManualJobDefinition>>(
  (ref) => ref.watch(operationsRepositoryProvider).availableJobs(),
);
final notificationsProvider = FutureProvider<List<NotificationItem>>(
  (ref) => ref.watch(operationsRepositoryProvider).notifications(),
);
final diagnosticsProvider = FutureProvider<List<DiagnosticDefinition>>(
  (ref) => ref.watch(operationsRepositoryProvider).diagnostics(),
);
