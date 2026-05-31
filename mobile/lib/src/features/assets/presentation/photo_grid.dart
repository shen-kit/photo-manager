import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../shared/models/models.dart';
import '../../../shared/providers.dart';
import '../../../shared/widgets/app_image.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../application/assets_controller.dart';
import '../data/assets_repository.dart';
import 'asset_detail_page.dart';

class PhotosPage extends ConsumerWidget {
  const PhotosPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(assetsControllerProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Photos'),
        actions: [
          IconButton(
            onPressed: () =>
                ref.read(assetsControllerProvider.notifier).load(force: true),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Stack(
        children: [
          AsyncStateWidget<PagedAssetsState>(
            value: state,
            isEmpty: (s) => s.items.isEmpty,
            empty: const EmptyState(
              message: 'No photos yet. Upload or scan from backend.',
            ),
            onRetry: () =>
                ref.read(assetsControllerProvider.notifier).load(force: true),
            data: (data) => TimelineGrid(
              state: data,
              onLoadMore: () =>
                  ref.read(assetsControllerProvider.notifier).loadMore(),
            ),
          ),
          const Positioned(
            right: 4,
            top: 16,
            bottom: 16,
            child: MonthFastScroller(),
          ),
        ],
      ),
    );
  }
}

class TimelineGrid extends ConsumerStatefulWidget {
  const TimelineGrid({
    super.key,
    required this.state,
    required this.onLoadMore,
  });
  final PagedAssetsState state;
  final VoidCallback onLoadMore;

  @override
  ConsumerState<TimelineGrid> createState() => _TimelineGridState();
}

class _TimelineGridState extends ConsumerState<TimelineGrid> {
  final _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      if (_controller.position.extentAfter < 800) widget.onLoadMore();
    });
  }

  @override
  Widget build(BuildContext context) {
    final grouped = groupByMonth(widget.state.items);
    final cells = <Object>[];
    for (final entry in grouped.entries) {
      cells.add(entry.key);
      cells.addAll(entry.value);
    }
    return CustomScrollView(
      controller: _controller,
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(4, 8, 28, 8),
          sliver: SliverGrid.builder(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 3,
              mainAxisSpacing: 2,
              crossAxisSpacing: 2,
            ),
            itemCount: cells.length,
            itemBuilder: (context, index) {
              final cell = cells[index];
              if (cell is String) return _MonthHeader(month: cell);
              final asset = cell as AssetGridItem;
              return AssetTile(
                asset: asset,
                allAssets: widget.state.items,
                index: widget.state.items.indexOf(asset),
              );
            },
          ),
        ),
        if (widget.state.isLoadingMore)
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
          ),
      ],
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}

Map<String, List<AssetGridItem>> groupByMonth(List<AssetGridItem> assets) {
  final formatter = DateFormat.yMMMM();
  final map = <String, List<AssetGridItem>>{};
  for (final asset in assets) {
    final date =
        asset.capturedAt ??
        DateTime.tryParse(asset.timelineDay) ??
        DateTime(1970);
    map.putIfAbsent(formatter.format(date), () => []).add(asset);
  }
  return map;
}

class _MonthHeader extends StatelessWidget {
  const _MonthHeader({required this.month});
  final String month;

  @override
  Widget build(BuildContext context) => Container(
    alignment: Alignment.bottomLeft,
    padding: const EdgeInsets.all(8),
    color: Theme.of(context).scaffoldBackgroundColor,
    child: Text(month, style: Theme.of(context).textTheme.titleMedium),
  );
}

class AssetTile extends ConsumerWidget {
  const AssetTile({
    super.key,
    required this.asset,
    required this.allAssets,
    required this.index,
  });
  final AssetGridItem asset;
  final List<AssetGridItem> allAssets;
  final int index;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.watch(apiClientProvider);
    return FutureBuilder<Map<String, String>>(
      future: api.authImageHeaders(),
      builder: (context, headers) => InkWell(
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                AssetDetailPage(assets: allAssets, initialIndex: index),
          ),
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            AppImage.network(
              api.mediaUri(asset.smallThumbnailUrl).toString(),
              headers: headers.data ?? const {},
              placeholderText: asset.blurhash == null ? null : '•••',
            ),
            if (asset.mediaKind == 'video')
              const Positioned(
                right: 4,
                top: 4,
                child: Icon(
                  Icons.play_circle_fill,
                  size: 18,
                  color: Colors.white70,
                ),
              ),
            if (asset.isFavorite)
              const Positioned(
                left: 4,
                top: 4,
                child: Icon(Icons.favorite, size: 16, color: Colors.white70),
              ),
          ],
        ),
      ),
    );
  }
}

class MonthFastScroller extends ConsumerWidget {
  const MonthFastScroller({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(assetFilterProvider);
    return FutureBuilder<List<TimelineMonth>>(
      future: ref.watch(assetsRepositoryProvider).months(filter),
      builder: (context, snapshot) {
        final months = snapshot.data ?? const <TimelineMonth>[];
        if (months.isEmpty) return const SizedBox.shrink();
        return RotatedBox(
          quarterTurns: 1,
          child: SizedBox(
            width: MediaQuery.sizeOf(context).height - 64,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: months.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, index) => ActionChip(
                visualDensity: VisualDensity.compact,
                label: RotatedBox(
                  quarterTurns: -1,
                  child: Text(
                    months[index].month.substring(0, 7),
                    style: const TextStyle(fontSize: 10),
                  ),
                ),
                onPressed: () {
                  ref.read(assetFilterProvider.notifier).state = AssetFilter(
                    month: months[index].month,
                  );
                },
              ),
            ),
          ),
        );
      },
    );
  }
}
