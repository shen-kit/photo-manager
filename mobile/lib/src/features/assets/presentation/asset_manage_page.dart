import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../../people/application/people_providers.dart';
import '../../tags/application/taxonomy_controller.dart';
import '../application/assets_controller.dart';

class AssetManagePage extends ConsumerWidget {
  const AssetManagePage({super.key, required this.assetId});
  final String assetId;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('Asset details')),
    body: FutureBuilder<AssetDetail>(
      future: ref.watch(assetsRepositoryProvider).detail(assetId, force: true),
      builder: (context, snapshot) {
        if (snapshot.hasError)
          return ErrorState(message: snapshot.error.toString());
        final detail = snapshot.data;
        if (detail == null)
          return const Center(child: CircularProgressIndicator());
        return ListView(
          padding: const EdgeInsets.all(12),
          children: [
            Text(
              detail.masterPath,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              detail.mimeType,
              style: const TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            _Section(
              title: 'Tags & albums',
              children: [
                Wrap(
                  spacing: 8,
                  children: detail.tags
                      .map(
                        (tag) => Chip(
                          label: Text(tag.path),
                          onDeleted: () async {
                            await ref
                                .read(assetsRepositoryProvider)
                                .removeTag(assetId, tag.id);
                          },
                        ),
                      )
                      .toList(),
                ),
                Row(
                  children: [
                    FilledButton.tonalIcon(
                      onPressed: () => _pickTag(context, ref, album: false),
                      icon: const Icon(Icons.sell_outlined),
                      label: const Text('Add tag'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton.tonalIcon(
                      onPressed: () => _pickTag(context, ref, album: true),
                      icon: const Icon(Icons.photo_album_outlined),
                      label: const Text('Add album'),
                    ),
                  ],
                ),
              ],
            ),
            _Section(
              title: 'People',
              children: [
                Wrap(
                  spacing: 8,
                  children: detail.people
                      .map((p) => Chip(label: Text(p.name ?? 'Unnamed')))
                      .toList(),
                ),
              ],
            ),
            _Section(
              title: 'Faces',
              children: [AssetFacesPanel(assetId: assetId)],
            ),
            _Section(
              title: 'Metadata',
              children: [
                Text(
                  'Captured: ${detail.capturedAt ?? detail.capturedAtLocal ?? 'unknown'}',
                ),
                Text('Size: ${detail.width ?? '?'} × ${detail.height ?? '?'}'),
                if (detail.durationSeconds != null)
                  Text('Duration: ${detail.durationSeconds}s'),
                if (detail.description != null) Text(detail.description!),
              ],
            ),
          ],
        );
      },
    ),
  );

  Future<void> _pickTag(
    BuildContext context,
    WidgetRef ref, {
    required bool album,
  }) async {
    final tags = await ref
        .read(taxonomyRepositoryProvider)
        .listTags(albums: album);
    if (!context.mounted) return;
    final selected = await showModalBottomSheet<TagNode>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          children: tags
              .map(
                (tag) => ListTile(
                  title: Text(tag.name),
                  subtitle: Text(tag.path),
                  onTap: () => Navigator.pop(context, tag),
                ),
              )
              .toList(),
        ),
      ),
    );
    if (selected == null) return;
    await ref.read(assetsRepositoryProvider).addTag(assetId, selected.id);
    if (context.mounted) Navigator.pop(context);
  }
}

class AssetFacesPanel extends ConsumerWidget {
  const AssetFacesPanel({super.key, required this.assetId});
  final String assetId;

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      FutureBuilder<List<AssetFace>>(
        future: ref.watch(facesRepositoryProvider).listForAsset(assetId),
        builder: (context, snapshot) {
          final faces = snapshot.data;
          if (snapshot.hasError)
            return Text(
              snapshot.error.toString(),
              style: const TextStyle(color: Colors.orangeAccent),
            );
          if (faces == null) return const LinearProgressIndicator();
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  FilledButton.tonal(
                    onPressed: () =>
                        ref.read(facesRepositoryProvider).process(assetId),
                    child: const Text('Process'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.tonal(
                    onPressed: () =>
                        ref.read(facesRepositoryProvider).match(assetId),
                    child: const Text('Match'),
                  ),
                ],
              ),
              if (faces.isEmpty) const Text('No faces'),
              ...faces.map(
                (face) => ListTile(
                  leading: const Icon(Icons.face),
                  title: Text(face.personId ?? 'Unassigned face'),
                  subtitle: Text(
                    face.isExcluded
                        ? 'Excluded'
                        : face.isConfirmed
                        ? 'Confirmed'
                        : 'Unconfirmed',
                  ),
                  trailing: Wrap(
                    spacing: 4,
                    children: [
                      IconButton(
                        tooltip: 'Confirm',
                        icon: const Icon(Icons.check),
                        onPressed: () => ref
                            .read(facesRepositoryProvider)
                            .patch(face.id, isConfirmed: true),
                      ),
                      IconButton(
                        tooltip: 'Exclude',
                        icon: const Icon(Icons.block),
                        onPressed: () => ref
                            .read(facesRepositoryProvider)
                            .patch(face.id, isExcluded: true),
                      ),
                      IconButton(
                        tooltip: 'Assign',
                        icon: const Icon(Icons.person_add_alt),
                        onPressed: () => _assign(context, ref, face.id),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      );

  Future<void> _assign(
    BuildContext context,
    WidgetRef ref,
    String faceId,
  ) async {
    final people = await ref
        .read(peopleRepositoryProvider)
        .list(includeHidden: true);
    if (!context.mounted) return;
    final person = await showModalBottomSheet<Person>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          children: people
              .map(
                (p) => ListTile(
                  title: Text(p.name ?? 'Unnamed'),
                  subtitle: Text('${p.assetCount} assets'),
                  onTap: () => Navigator.pop(context, p),
                ),
              )
              .toList(),
        ),
      ),
    );
    if (person != null)
      await ref
          .read(facesRepositoryProvider)
          .patch(faceId, personId: person.id, isExcluded: false);
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
    ),
  );
}
