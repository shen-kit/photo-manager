import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../../assets/data/assets_repository.dart';
import '../../assets/presentation/photo_grid.dart';
import '../../tags/application/taxonomy_controller.dart';

class AlbumsPage extends ConsumerWidget {
  const AlbumsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final albums = ref.watch(albumsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Albums'),
        actions: [
          IconButton(
            onPressed: () => _create(context, ref),
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: AsyncStateWidget<List<TagNode>>(
        value: albums,
        isEmpty: (items) => items.isEmpty,
        empty: const EmptyState(message: 'No albums yet'),
        onRetry: () => ref.invalidate(albumsProvider),
        data: (items) => ListView.separated(
          padding: const EdgeInsets.all(12),
          itemBuilder: (context, index) => ListTile(
            leading: const Icon(Icons.photo_album_outlined),
            title: Text(items[index].name),
            subtitle: Text(items[index].path),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => AlbumDetailPage(album: items[index]),
              ),
            ),
          ),
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemCount: items.length,
        ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create album'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    if (name == null || name.trim().isEmpty) return;
    await ref
        .read(taxonomyRepositoryProvider)
        .create(album: true, name: name.trim());
    ref.invalidate(albumsProvider);
  }
}

class AlbumDetailPage extends ConsumerStatefulWidget {
  const AlbumDetailPage({super.key, required this.album});
  final TagNode album;

  @override
  ConsumerState<AlbumDetailPage> createState() => _AlbumDetailPageState();
}

class _AlbumDetailPageState extends ConsumerState<AlbumDetailPage> {
  Future<PagedAssetsState>? _future;

  @override
  void initState() {
    super.initState();
    _future = ref
        .read(taxonomyRepositoryProvider)
        .assets(album: true, id: widget.album.id);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.album.name)),
    body: FutureBuilder<PagedAssetsState>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.hasError)
          return ErrorState(
            message: snapshot.error.toString(),
            onRetry: () => setState(
              () => _future = ref
                  .read(taxonomyRepositoryProvider)
                  .assets(album: true, id: widget.album.id),
            ),
          );
        if (!snapshot.hasData)
          return const Center(child: CircularProgressIndicator());
        return TimelineGrid(state: snapshot.data!, onLoadMore: () {});
      },
    ),
  );
}
