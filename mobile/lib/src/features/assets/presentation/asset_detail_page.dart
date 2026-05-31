import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../../../shared/widgets/app_image.dart';
import '../../../shared/widgets/confirm_dialog.dart';
import '../../backup/application/backup_controller.dart';
import '../application/assets_controller.dart';
import 'asset_manage_page.dart';

class AssetDetailPage extends ConsumerStatefulWidget {
  const AssetDetailPage({
    super.key,
    required this.assets,
    required this.initialIndex,
  });
  final List<AssetGridItem> assets;
  final int initialIndex;

  @override
  ConsumerState<AssetDetailPage> createState() => _AssetDetailPageState();
}

class _AssetDetailPageState extends ConsumerState<AssetDetailPage> {
  late final PageController _pageController;
  late int _index;

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex;
    _pageController = PageController(initialPage: _index);
    WidgetsBinding.instance.addPostFrameCallback((_) => _prefetch());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        actions: [
          IconButton(
            onPressed: _editDateTime,
            icon: const Icon(Icons.calendar_month),
          ),
          IconButton(
            onPressed: _toggleFavorite,
            icon: const Icon(Icons.favorite_border),
          ),
          IconButton(onPressed: _openManage, icon: const Icon(Icons.more_vert)),
          IconButton(
            onPressed: _softDelete,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _pageController,
              itemCount: widget.assets.length,
              onPageChanged: (value) {
                setState(() => _index = value);
                _prefetch();
              },
              itemBuilder: (context, index) =>
                  AssetPreview(asset: widget.assets[index]),
            ),
          ),
          _ThumbnailStrip(
            assets: widget.assets,
            selected: _index,
            onSelected: (i) => _pageController.animateToPage(
              i,
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _prefetch() async {
    final ids = <String>[];
    for (var i = _index - 2; i <= _index + 2; i++) {
      if (i >= 0 && i < widget.assets.length) ids.add(widget.assets[i].id);
    }
    if (ids.isNotEmpty)
      await ref
          .read(assetsRepositoryProvider)
          .ensurePreviews(ids, priority: 'interactive')
          .catchError((_) => <AssetPreviewEnsureItem>[]);
  }

  Future<AssetDetail> _detail() =>
      ref.read(assetsRepositoryProvider).detail(widget.assets[_index].id);

  Future<void> _toggleFavorite() async {
    final detail = await _detail();
    await ref
        .read(assetsRepositoryProvider)
        .update(detail.id, isFavorite: !detail.isFavorite);
    if (mounted)
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Updated favorite')));
  }

  Future<void> _editDateTime() async {
    final detail = await _detail();
    if (!mounted) return;
    final date = await showDatePicker(
      context: context,
      firstDate: DateTime(1900),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      initialDate: detail.capturedAt ?? DateTime.now(),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(detail.capturedAt ?? DateTime.now()),
    );
    if (time == null) return;
    final updated = DateTime(
      date.year,
      date.month,
      date.day,
      time.hour,
      time.minute,
    );
    await ref
        .read(assetsRepositoryProvider)
        .update(detail.id, capturedAt: updated);
    if (mounted)
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Date/time updated')));
  }

  void _openManage() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AssetManagePage(assetId: widget.assets[_index].id),
      ),
    );
  }

  Future<void> _softDelete() async {
    final ok = await confirmDestructive(
      context,
      title: 'Move to trash?',
      message:
          'This asset is moved to trash. Originals are not permanently deleted.',
      action: 'Move',
    );
    if (!ok) return;
    await ref
        .read(assetsControllerProvider.notifier)
        .deleteAsset(widget.assets[_index].id);
    if (mounted) Navigator.pop(context);
  }
}

class AssetPreview extends ConsumerWidget {
  const AssetPreview({super.key, required this.asset});
  final AssetGridItem asset;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return FutureBuilder<AssetDetail>(
      future: ref.watch(assetsRepositoryProvider).detail(asset.id),
      builder: (context, snapshot) {
        final detail = snapshot.data;
        if (detail == null)
          return AppImage.network(
            ref
                .watch(apiClientProvider)
                .mediaUri(asset.smallThumbnailUrl)
                .toString(),
            fit: BoxFit.contain,
          );
        return FutureBuilder<File?>(
          future: ref
              .watch(localMediaRepositoryProvider)
              .resolveLocalFile(detail),
          builder: (context, local) {
            if (local.data != null)
              return AppImage.file(local.data!, fit: BoxFit.contain);
            if (detail.mediaKind == 'video' ||
                detail.mimeType.startsWith('video/'))
              return VideoPreview(
                url: ref
                    .watch(apiClientProvider)
                    .mediaUri(detail.previewUrl)
                    .toString(),
              );
            return FutureBuilder<Map<String, String>>(
              future: ref.watch(apiClientProvider).authImageHeaders(),
              builder: (context, headers) => AppImage.network(
                ref
                    .watch(apiClientProvider)
                    .mediaUri(detail.previewUrl)
                    .toString(),
                headers: headers.data ?? const {},
                fit: BoxFit.contain,
              ),
            );
          },
        );
      },
    );
  }
}

class VideoPreview extends StatefulWidget {
  const VideoPreview({super.key, required this.url});
  final String url;

  @override
  State<VideoPreview> createState() => _VideoPreviewState();
}

class _VideoPreviewState extends State<VideoPreview> {
  VideoPlayerController? _controller;

  @override
  void initState() {
    super.initState();
    _controller = VideoPlayerController.networkUrl(Uri.parse(widget.url))
      ..initialize().then((_) => setState(() {}));
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized)
      return const Center(child: CircularProgressIndicator());
    return Stack(
      alignment: Alignment.center,
      children: [
        AspectRatio(
          aspectRatio: controller.value.aspectRatio,
          child: VideoPlayer(controller),
        ),
        IconButton.filledTonal(
          onPressed: () => setState(
            () => controller.value.isPlaying
                ? controller.pause()
                : controller.play(),
          ),
          icon: Icon(
            controller.value.isPlaying ? Icons.pause : Icons.play_arrow,
          ),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }
}

class _ThumbnailStrip extends ConsumerWidget {
  const _ThumbnailStrip({
    required this.assets,
    required this.selected,
    required this.onSelected,
  });
  final List<AssetGridItem> assets;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.watch(apiClientProvider);
    return SizedBox(
      height: 86,
      child: FutureBuilder<Map<String, String>>(
        future: api.authImageHeaders(),
        builder: (context, headers) => ListView.separated(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          scrollDirection: Axis.horizontal,
          itemCount: assets.length,
          separatorBuilder: (_, __) => const SizedBox(width: 6),
          itemBuilder: (context, index) => GestureDetector(
            onTap: () => onSelected(index),
            child: Container(
              width: 58,
              decoration: BoxDecoration(
                border: Border.all(
                  color: index == selected ? Colors.white : Colors.transparent,
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              clipBehavior: Clip.antiAlias,
              child: AppImage.network(
                api.mediaUri(assets[index].smallThumbnailUrl).toString(),
                headers: headers.data ?? const {},
              ),
            ),
          ),
        ),
      ),
    );
  }
}
