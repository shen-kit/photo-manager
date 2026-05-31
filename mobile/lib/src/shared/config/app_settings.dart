import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';

class AppSettingsStore {
  AppSettingsStore(this._prefs);
  static const _baseUrlKey = 'backend_base_url';
  static const _selectedBackupSourcesKey = 'selected_backup_sources';
  static const _recentSearchesKey = 'recent_searches';
  static const _localIndexKey = 'local_media_index';

  final SharedPreferences _prefs;

  String get baseUrl => _prefs.getString(_baseUrlKey) ?? 'http://10.0.2.2:8000';

  Future<void> setBaseUrl(String value) async {
    final normalized = normalizeBaseUrl(value);
    await _prefs.setString(_baseUrlKey, normalized);
  }

  static String normalizeBaseUrl(String value) {
    final trimmed = value.trim();
    final uri = Uri.tryParse(trimmed);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw FormatException(
        'Enter a valid backend URL including http:// or https://',
      );
    }
    return trimmed.endsWith('/')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }

  Set<String> get selectedBackupSourceIds =>
      (_prefs.getStringList(_selectedBackupSourcesKey) ?? const []).toSet();

  Future<void> setSelectedBackupSourceIds(Set<String> ids) =>
      _prefs.setStringList(_selectedBackupSourcesKey, ids.toList()..sort());

  List<String> get recentSearches =>
      _prefs.getStringList(_recentSearchesKey) ?? const [];

  Future<void> addRecentSearch(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) return;
    final next = [
      trimmed,
      ...recentSearches.where((q) => q != trimmed),
    ].take(10).toList();
    await _prefs.setStringList(_recentSearchesKey, next);
  }

  List<LocalMediaItem> get localIndex {
    final raw = _prefs.getString(_localIndexKey);
    if (raw == null || raw.isEmpty) return const [];
    final decoded = jsonDecode(raw);
    return decoded is List
        ? decoded
              .whereType<Map>()
              .map((e) => LocalMediaItem.fromJson(e.cast<String, dynamic>()))
              .toList()
        : const [];
  }

  Future<void> setLocalIndex(List<LocalMediaItem> items) => _prefs.setString(
    _localIndexKey,
    jsonEncode(items.map((e) => e.toJson()).toList()),
  );

  Future<void> clearLocalCache() async {
    await _prefs.remove(_localIndexKey);
  }
}
