import 'dart:convert';

DateTime? parseDateTime(Object? value) =>
    value is String ? DateTime.tryParse(value) : null;
String? dateString(DateTime? value) => value?.toUtc().toIso8601String();

Map<String, dynamic>? asMap(Object? value) =>
    value is Map ? value.cast<String, dynamic>() : null;

List<Map<String, dynamic>> asMapList(Object? value) => value is List
    ? value.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
    : const [];

class User {
  const User({
    required this.id,
    required this.username,
    required this.isActive,
  });
  final String id;
  final String username;
  final bool isActive;

  factory User.fromJson(Map<String, dynamic> json) => User(
    id: json['id'] as String,
    username: json['username'] as String,
    isActive: json['is_active'] as bool? ?? false,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'is_active': isActive,
  };
}

class AuthResponse {
  const AuthResponse({
    required this.accessToken,
    required this.expiresIn,
    required this.user,
  });
  final String accessToken;
  final int expiresIn;
  final User user;

  factory AuthResponse.fromJson(Map<String, dynamic> json) => AuthResponse(
    accessToken: json['access_token'] as String,
    expiresIn: json['expires_in'] as int? ?? 0,
    user: User.fromJson(json['user'] as Map<String, dynamic>),
  );
}

class AssetGridItem {
  const AssetGridItem({
    required this.id,
    required this.mimeType,
    required this.mediaKind,
    required this.timelineDay,
    required this.isFavorite,
    required this.hasLargePreview,
    required this.smallThumbnailUrl,
    this.capturedAt,
    this.width,
    this.height,
    this.durationSeconds,
    this.blurhash,
    this.fileHash,
    this.masterPath,
    this.fileSizeBytes,
  });

  final String id;
  final String mimeType;
  final String mediaKind;
  final DateTime? capturedAt;
  final String timelineDay;
  final bool isFavorite;
  final int? width;
  final int? height;
  final double? durationSeconds;
  final bool hasLargePreview;
  final String smallThumbnailUrl;
  final String? blurhash;
  final String? fileHash;
  final String? masterPath;
  final int? fileSizeBytes;

  factory AssetGridItem.fromJson(Map<String, dynamic> json) => AssetGridItem(
    id: json['id'] as String,
    mimeType: json['mime_type'] as String? ?? 'application/octet-stream',
    mediaKind:
        json['media_kind'] as String? ??
        (json['mime_type'] as String? ?? '').split('/').first,
    capturedAt: parseDateTime(json['captured_at']),
    timelineDay:
        json['timeline_day'] as String? ??
        (json['captured_at'] as String? ?? '').split('T').first,
    isFavorite: json['is_favorite'] as bool? ?? false,
    width: json['width'] as int?,
    height: json['height'] as int?,
    durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
    hasLargePreview: json['has_large_preview'] as bool? ?? false,
    smallThumbnailUrl: json['small_thumbnail_url'] as String? ?? '',
    blurhash: json['blurhash'] as String?,
    fileHash: json['file_hash'] as String?,
    masterPath: json['master_path'] as String?,
    fileSizeBytes: json['file_size_bytes'] as int?,
  );
}

class AssetGridPage {
  const AssetGridPage({
    required this.items,
    required this.hasMore,
    this.nextCursor,
  });
  final List<AssetGridItem> items;
  final bool hasMore;
  final String? nextCursor;

  factory AssetGridPage.fromJson(Map<String, dynamic> json) => AssetGridPage(
    items: (json['items'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => AssetGridItem.fromJson(e.cast<String, dynamic>()))
        .toList(),
    hasMore: json['has_more'] as bool? ?? false,
    nextCursor: json['next_cursor'] as String?,
  );
}

class TagSummary {
  const TagSummary({
    required this.id,
    required this.name,
    required this.slug,
    required this.path,
    required this.isAlbum,
    this.coverAssetId,
  });
  final int id;
  final String name;
  final String slug;
  final String path;
  final bool isAlbum;
  final String? coverAssetId;

  factory TagSummary.fromJson(Map<String, dynamic> json) => TagSummary(
    id: json['id'] as int,
    name: json['name'] as String,
    slug: json['slug'] as String? ?? '',
    path: json['path'] as String,
    isAlbum: json['is_album'] as bool? ?? false,
    coverAssetId: json['cover_asset_id'] as String?,
  );
}

class TagNode extends TagSummary {
  const TagNode({
    required super.id,
    required super.name,
    required super.slug,
    required super.path,
    required super.isAlbum,
    super.coverAssetId,
    this.parentPath,
    this.description,
    this.createdAt,
    this.updatedAt,
  });
  final String? parentPath;
  final String? description;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory TagNode.fromJson(Map<String, dynamic> json) => TagNode(
    id: json['id'] as int,
    name: json['name'] as String,
    slug: json['slug'] as String? ?? '',
    path: json['path'] as String,
    isAlbum: json['is_album'] as bool? ?? false,
    coverAssetId: json['cover_asset_id'] as String?,
    parentPath: json['parent_path'] as String?,
    description: json['description'] as String?,
    createdAt: parseDateTime(json['created_at']),
    updatedAt: parseDateTime(json['updated_at']),
  );

  Map<String, dynamic> mutationJson({
    String? name,
    int? parentId,
    String? description,
    String? coverAssetId,
  }) => {
    if (name != null) 'name': name,
    if (parentId != null) 'parent_id': parentId,
    if (description != null) 'description': description,
    if (coverAssetId != null) 'cover_asset_id': coverAssetId,
  };
}

class PersonSummary {
  const PersonSummary({this.id, this.name});
  final String? id;
  final String? name;

  factory PersonSummary.fromJson(Map<String, dynamic> json) =>
      PersonSummary(id: json['id'] as String?, name: json['name'] as String?);
}

class FaceSummary {
  const FaceSummary({required this.id, this.person});
  final String id;
  final PersonSummary? person;

  factory FaceSummary.fromJson(Map<String, dynamic> json) => FaceSummary(
    id: json['id'] as String,
    person: json['person'] is Map
        ? PersonSummary.fromJson(
            (json['person'] as Map).cast<String, dynamic>(),
          )
        : null,
  );
}

class AssetDetail extends AssetGridItem {
  const AssetDetail({
    required super.id,
    required this.fileHash,
    required this.masterPath,
    required super.mimeType,
    required super.isFavorite,
    required super.hasLargePreview,
    required super.smallThumbnailUrl,
    required this.previewUrl,
    required this.createdAt,
    super.mediaKind = '',
    super.timelineDay = '',
    super.capturedAt,
    super.width,
    super.height,
    super.durationSeconds,
    super.blurhash,
    this.capturedAtLocal,
    this.description,
    this.fileSizeBytes,
    this.previewStatus,
    this.exifData,
    this.tags = const [],
    this.people = const [],
    this.faces = const [],
  }) : super(
         fileHash: fileHash,
         masterPath: masterPath,
         fileSizeBytes: fileSizeBytes,
       );

  @override
  final String fileHash;
  @override
  final String masterPath;
  final String? capturedAtLocal;
  final String? description;
  @override
  final int? fileSizeBytes;
  final String? previewStatus;
  final Map<String, dynamic>? exifData;
  final List<TagSummary> tags;
  final List<PersonSummary> people;
  final List<FaceSummary> faces;
  final String previewUrl;
  final DateTime createdAt;

  factory AssetDetail.fromJson(Map<String, dynamic> json) => AssetDetail(
    id: json['id'] as String,
    fileHash: json['file_hash'] as String,
    masterPath: json['master_path'] as String,
    mimeType: json['mime_type'] as String,
    mediaKind: (json['mime_type'] as String).split('/').first,
    capturedAt: parseDateTime(json['captured_at']),
    timelineDay: (json['captured_at'] as String? ?? '').split('T').first,
    capturedAtLocal: json['captured_at_local'] as String?,
    description: json['description'] as String?,
    isFavorite: json['is_favorite'] as bool? ?? false,
    width: json['width'] as int?,
    height: json['height'] as int?,
    durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
    hasLargePreview: json['has_large_preview'] as bool? ?? false,
    fileSizeBytes: json['file_size_bytes'] as int?,
    previewStatus: json['preview_status'] as String?,
    blurhash: json['blurhash'] as String?,
    exifData: asMap(json['exif_data']),
    tags: asMapList(json['tags']).map(TagSummary.fromJson).toList(),
    people: asMapList(json['people']).map(PersonSummary.fromJson).toList(),
    faces: asMapList(json['faces']).map(FaceSummary.fromJson).toList(),
    smallThumbnailUrl: json['small_thumbnail_url'] as String? ?? '',
    previewUrl: json['preview_url'] as String? ?? '',
    createdAt:
        parseDateTime(json['created_at']) ??
        DateTime.fromMillisecondsSinceEpoch(0),
  );
}

class AssetPreviewEnsureItem {
  const AssetPreviewEnsureItem({
    required this.assetId,
    required this.status,
    this.previewUrl,
    this.jobId,
    this.error,
  });
  final String assetId;
  final String status;
  final String? previewUrl;
  final String? jobId;
  final String? error;

  factory AssetPreviewEnsureItem.fromJson(Map<String, dynamic> json) =>
      AssetPreviewEnsureItem(
        assetId: json['asset_id'] as String,
        status: json['status'] as String,
        previewUrl: json['preview_url'] as String?,
        jobId: json['job_id'] as String?,
        error: json['error'] as String?,
      );
}

class TimelineMonth {
  const TimelineMonth({
    required this.month,
    required this.assetCount,
    this.cover,
  });
  final String month;
  final int assetCount;
  final AssetGridItem? cover;

  factory TimelineMonth.fromJson(Map<String, dynamic> json) => TimelineMonth(
    month: json['month'] as String,
    assetCount: json['asset_count'] as int? ?? 0,
    cover: json['cover'] is Map
        ? AssetGridItem.fromJson({
            ...(json['cover'] as Map).cast<String, dynamic>(),
            'timeline_day': (json['month'] as String).replaceFirst(
              '-01',
              '-01',
            ),
            'mime_type': 'image/*',
            'is_favorite': false,
            'has_large_preview': false,
          })
        : null,
  );
}

class Person {
  const Person({
    required this.id,
    required this.faceCount,
    required this.assetCount,
    required this.isHidden,
    required this.thumbnailManuallySet,
    this.name,
    this.thumbnailUrl,
    this.thumbnailFaceId,
  });
  final String id;
  final String? name;
  final String? thumbnailUrl;
  final String? thumbnailFaceId;
  final bool thumbnailManuallySet;
  final int faceCount;
  final int assetCount;
  final bool isHidden;

  factory Person.fromJson(Map<String, dynamic> json) => Person(
    id: json['id'] as String,
    name: json['name'] as String?,
    thumbnailUrl: json['thumbnail_url'] as String?,
    thumbnailFaceId: json['thumbnail_face_id'] as String?,
    thumbnailManuallySet: json['thumbnail_manually_set'] as bool? ?? false,
    faceCount: json['face_count'] as int? ?? 0,
    assetCount: json['asset_count'] as int? ?? 0,
    isHidden: json['is_hidden'] as bool? ?? false,
  );
}

class AssetFace {
  const AssetFace({
    required this.id,
    required this.isConfirmed,
    required this.isExcluded,
    this.assetId,
    this.personId,
    this.cropUrl,
    this.confidence,
  });
  final String id;
  final String? assetId;
  final String? personId;
  final String? cropUrl;
  final double? confidence;
  final bool isConfirmed;
  final bool isExcluded;

  factory AssetFace.fromJson(Map<String, dynamic> json) => AssetFace(
    id: json['id'] as String,
    assetId: json['asset_id'] as String?,
    personId: json['person_id'] as String?,
    cropUrl: json['crop_url'] as String?,
    confidence: (json['detection_confidence'] as num?)?.toDouble(),
    isConfirmed: json['is_confirmed'] as bool? ?? false,
    isExcluded: json['is_excluded'] as bool? ?? false,
  );
}

class JobRead {
  const JobRead({
    required this.id,
    required this.type,
    required this.status,
    required this.progressCurrent,
    required this.isVisible,
    required this.createdAt,
    this.jobKey,
    this.progressTotal,
    this.progressMessage,
    this.errorMessage,
    this.result,
    this.parameters,
    this.queueName,
  });
  final String id;
  final String type;
  final String status;
  final String? jobKey;
  final int progressCurrent;
  final int? progressTotal;
  final String? progressMessage;
  final String? errorMessage;
  final bool isVisible;
  final DateTime createdAt;
  final Map<String, dynamic>? result;
  final Map<String, dynamic>? parameters;
  final String? queueName;

  bool get isActive => status == 'queued' || status == 'running';

  factory JobRead.fromJson(Map<String, dynamic> json) => JobRead(
    id: json['id'] as String,
    type: json['type'] as String,
    status: json['status'] as String,
    jobKey: json['job_key'] as String?,
    progressCurrent: json['progress_current'] as int? ?? 0,
    progressTotal: json['progress_total'] as int?,
    progressMessage: json['progress_message'] as String?,
    errorMessage: json['error_message'] as String?,
    isVisible: json['is_visible'] as bool? ?? true,
    createdAt:
        parseDateTime(json['created_at']) ??
        DateTime.fromMillisecondsSinceEpoch(0),
    result: asMap(json['result']),
    parameters: asMap(json['parameters']),
    queueName: json['queue_name'] as String?,
  );
}

class ManualJobDefinition {
  const ManualJobDefinition({
    required this.jobKey,
    required this.title,
    required this.description,
    required this.category,
    required this.mode,
    required this.supportsDryRun,
    this.activeJobId,
    this.activeStatus,
    this.defaultParams = const {},
  });
  final String jobKey;
  final String title;
  final String description;
  final String category;
  final String mode;
  final bool supportsDryRun;
  final String? activeJobId;
  final String? activeStatus;
  final Map<String, dynamic> defaultParams;

  bool get isActive => activeStatus == 'queued' || activeStatus == 'running';

  factory ManualJobDefinition.fromJson(Map<String, dynamic> json) =>
      ManualJobDefinition(
        jobKey: json['job_key'] as String,
        title: json['title'] as String,
        description: json['description'] as String? ?? '',
        category: json['category'] as String? ?? '',
        mode: json['mode'] as String? ?? '',
        supportsDryRun: json['supports_dry_run'] as bool? ?? false,
        activeJobId: json['active_job_id'] as String?,
        activeStatus: json['active_status'] as String?,
        defaultParams: asMap(json['default_params']) ?? const {},
      );
}

class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.level,
    required this.category,
    required this.title,
    required this.createdAt,
    this.message,
    this.readAt,
    this.details,
  });
  final String id;
  final String level;
  final String category;
  final String title;
  final String? message;
  final DateTime createdAt;
  final DateTime? readAt;
  final Map<String, dynamic>? details;

  bool get isUnread => readAt == null;

  factory NotificationItem.fromJson(Map<String, dynamic> json) =>
      NotificationItem(
        id: json['id'] as String,
        level: json['level'] as String,
        category: json['category'] as String,
        title: json['title'] as String,
        message: json['message'] as String?,
        createdAt:
            parseDateTime(json['created_at']) ??
            DateTime.fromMillisecondsSinceEpoch(0),
        readAt: parseDateTime(json['read_at']),
        details: asMap(json['details']),
      );
}

class TrashAsset extends AssetGridItem {
  const TrashAsset({
    required super.id,
    required this.deletedAt,
    required super.isFavorite,
    required super.hasLargePreview,
    required super.smallThumbnailUrl,
    super.mimeType = 'image/*',
    super.mediaKind = 'image',
    super.timelineDay = '',
    super.capturedAt,
    super.width,
    super.height,
    super.blurhash,
    this.description,
  });
  final DateTime deletedAt;
  final String? description;

  factory TrashAsset.fromJson(Map<String, dynamic> json) => TrashAsset(
    id: json['id'] as String,
    deletedAt:
        parseDateTime(json['deleted_at']) ??
        DateTime.fromMillisecondsSinceEpoch(0),
    capturedAt: parseDateTime(json['captured_at']),
    description: json['description'] as String?,
    isFavorite: json['is_favorite'] as bool? ?? false,
    hasLargePreview: json['has_large_preview'] as bool? ?? false,
    smallThumbnailUrl: json['small_thumbnail_url'] as String? ?? '',
    width: json['width'] as int?,
    height: json['height'] as int?,
    blurhash: json['blurhash'] as String?,
  );
}

class TrashPage {
  const TrashPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.total,
  });
  final List<TrashAsset> items;
  final int page;
  final int pageSize;
  final int total;

  factory TrashPage.fromJson(Map<String, dynamic> json) => TrashPage(
    items: asMapList(json['items']).map(TrashAsset.fromJson).toList(),
    page: json['page'] as int? ?? 1,
    pageSize: json['page_size'] as int? ?? 50,
    total: json['total'] as int? ?? 0,
  );
}

class DiagnosticDefinition {
  const DiagnosticDefinition({
    required this.key,
    required this.title,
    required this.description,
    required this.supportsRepair,
    this.latestStatus,
    this.latestHealthState,
    this.latestRunId,
  });
  final String key;
  final String title;
  final String description;
  final bool supportsRepair;
  final String? latestStatus;
  final String? latestHealthState;
  final String? latestRunId;

  factory DiagnosticDefinition.fromJson(Map<String, dynamic> json) =>
      DiagnosticDefinition(
        key: json['key'] as String,
        title: json['title'] as String,
        description: json['description'] as String? ?? '',
        supportsRepair: json['supports_repair'] as bool? ?? false,
        latestStatus: json['latest_status'] as String?,
        latestHealthState: json['latest_health_state'] as String?,
        latestRunId: json['latest_run_id'] as String?,
      );
}

class LocalMediaItem {
  const LocalMediaItem({
    required this.id,
    required this.uri,
    required this.filename,
    required this.mediaKind,
    this.bucketId,
    this.bucketName,
    this.sizeBytes,
    this.createdAt,
    this.modifiedAt,
    this.mimeType,
    this.sha256,
    this.isAvailable = true,
    this.matchedAssetId,
    this.uploadState = UploadState.pending,
    this.lastError,
    this.retryCount = 0,
  });
  final String id;
  final String uri;
  final String filename;
  final String mediaKind;
  final String? bucketId;
  final String? bucketName;
  final int? sizeBytes;
  final DateTime? createdAt;
  final DateTime? modifiedAt;
  final String? mimeType;
  final String? sha256;
  final bool isAvailable;
  final String? matchedAssetId;
  final UploadState uploadState;
  final String? lastError;
  final int retryCount;

  LocalMediaItem copyWith({
    String? sha256,
    bool? isAvailable,
    String? matchedAssetId,
    UploadState? uploadState,
    String? lastError,
    int? retryCount,
  }) => LocalMediaItem(
    id: id,
    uri: uri,
    filename: filename,
    mediaKind: mediaKind,
    bucketId: bucketId,
    bucketName: bucketName,
    sizeBytes: sizeBytes,
    createdAt: createdAt,
    modifiedAt: modifiedAt,
    mimeType: mimeType,
    sha256: sha256 ?? this.sha256,
    isAvailable: isAvailable ?? this.isAvailable,
    matchedAssetId: matchedAssetId ?? this.matchedAssetId,
    uploadState: uploadState ?? this.uploadState,
    lastError: lastError,
    retryCount: retryCount ?? this.retryCount,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'uri': uri,
    'filename': filename,
    'media_kind': mediaKind,
    'bucket_id': bucketId,
    'bucket_name': bucketName,
    'size_bytes': sizeBytes,
    'created_at': dateString(createdAt),
    'modified_at': dateString(modifiedAt),
    'mime_type': mimeType,
    'sha256': sha256,
    'is_available': isAvailable,
    'matched_asset_id': matchedAssetId,
    'upload_state': uploadState.name,
    'last_error': lastError,
    'retry_count': retryCount,
  };

  factory LocalMediaItem.fromJson(Map<String, dynamic> json) => LocalMediaItem(
    id: json['id'] as String,
    uri: json['uri'] as String,
    filename: json['filename'] as String,
    mediaKind: json['media_kind'] as String,
    bucketId: json['bucket_id'] as String?,
    bucketName: json['bucket_name'] as String?,
    sizeBytes: json['size_bytes'] as int?,
    createdAt: parseDateTime(json['created_at']),
    modifiedAt: parseDateTime(json['modified_at']),
    mimeType: json['mime_type'] as String?,
    sha256: json['sha256'] as String?,
    isAvailable: json['is_available'] as bool? ?? true,
    matchedAssetId: json['matched_asset_id'] as String?,
    uploadState: UploadState.values.firstWhere(
      (e) => e.name == json['upload_state'],
      orElse: () => UploadState.pending,
    ),
    lastError: json['last_error'] as String?,
    retryCount: json['retry_count'] as int? ?? 0,
  );
}

enum UploadState { pending, matched, uploading, uploaded, failed }

class BackupSource {
  const BackupSource({
    required this.id,
    required this.name,
    required this.assetCount,
    this.selected = false,
  });
  final String id;
  final String name;
  final int assetCount;
  final bool selected;

  BackupSource copyWith({bool? selected}) => BackupSource(
    id: id,
    name: name,
    assetCount: assetCount,
    selected: selected ?? this.selected,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'asset_count': assetCount,
    'selected': selected,
  };
  factory BackupSource.fromJson(Map<String, dynamic> json) => BackupSource(
    id: json['id'] as String,
    name: json['name'] as String,
    assetCount: json['asset_count'] as int? ?? 0,
    selected: json['selected'] as bool? ?? false,
  );
}

class SearchStateData {
  const SearchStateData({
    this.query = '',
    this.personIds = const [],
    this.tagIds = const [],
  });
  final String query;
  final List<String> personIds;
  final List<int> tagIds;
}

String encodePretty(Object? value) =>
    const JsonEncoder.withIndent('  ').convert(value);
