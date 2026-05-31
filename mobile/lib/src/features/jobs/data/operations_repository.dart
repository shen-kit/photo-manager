import '../../../shared/api/api_client.dart';
import '../../../shared/models/models.dart';

class OperationsRepository {
  OperationsRepository(this._api);
  final ApiClient _api;

  Future<List<JobRead>> jobs() => _api.getJson(
    '/jobs/',
    (json) => (json as List)
        .whereType<Map>()
        .map((e) => JobRead.fromJson(e.cast<String, dynamic>()))
        .toList(),
    query: {'limit': 100},
  );
  Future<List<ManualJobDefinition>> availableJobs() => _api.getJson(
    '/jobs/available',
    (json) => asMapList(
      (json as Map)['items'],
    ).map(ManualJobDefinition.fromJson).toList(),
  );
  Future<JobRead> runJob(String key, [Map<String, dynamic>? params]) =>
      _api.postJson(
        '/jobs/$key/run',
        params == null ? null : {'params': params},
        (json) => JobRead.fromJson(
          ((json as Map)['job'] as Map).cast<String, dynamic>(),
        ),
      );
  Future<List<NotificationItem>> notifications({bool unreadOnly = false}) =>
      _api.getJson(
        '/notifications/',
        (json) => (json as List)
            .whereType<Map>()
            .map((e) => NotificationItem.fromJson(e.cast<String, dynamic>()))
            .toList(),
        query: {'limit': 100, 'unread_only': unreadOnly},
      );
  Future<void> markAllRead() =>
      _api.postJson('/notifications/read-all', null, (_) => null);
  Future<void> markRead(String id) =>
      _api.postJson('/notifications/$id/read', null, (_) => null);
  Future<void> deleteNotification(String id) =>
      _api.delete('/notifications/$id');
  Future<void> deleteAllNotifications() => _api.delete('/notifications/');
  Future<List<DiagnosticDefinition>> diagnostics() => _api.getJson(
    '/system/integrity/diagnostics',
    (json) => asMapList(
      (json as Map)['items'],
    ).map(DiagnosticDefinition.fromJson).toList(),
  );
  Future<void> runDiagnostic(String key) => _api.postJson(
    '/system/integrity/diagnostics/$key/run',
    null,
    (_) => null,
  );
  Future<void> repairRun(String runId) =>
      _api.postJson('/system/integrity/runs/$runId/repair', null, (_) => null);
}
