import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/widgets/async_state_widget.dart';
import '../application/backup_controller.dart';

class DeviceFoldersPage extends ConsumerWidget {
  const DeviceFoldersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('Device folders')),
    body: AsyncStateWidget(
      value: ref.watch(backupSourcesProvider),
      isEmpty: (items) => items.isEmpty,
      empty: EmptyState(
        message: 'No media access or folders found',
        action: FilledButton(
          onPressed: () => ref.invalidate(backupSourcesProvider),
          child: const Text('Request access'),
        ),
      ),
      onRetry: () => ref.invalidate(backupSourcesProvider),
      data: (sources) => ListView(
        children: [
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'Select folders/albums for automatic backup. Nothing is selected by default.',
              style: TextStyle(color: Colors.white70),
            ),
          ),
          ...sources.map(
            (source) => SwitchListTile(
              value: source.selected,
              title: Text(source.name),
              subtitle: Text('${source.assetCount} items'),
              onChanged: (value) async {
                await ref
                    .read(localMediaRepositoryProvider)
                    .setSourceSelected(source.id, value);
                ref.invalidate(backupSourcesProvider);
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: FilledButton.icon(
              onPressed: () async {
                await ref
                    .read(localMediaRepositoryProvider)
                    .scanSelectedSources();
                ref.invalidate(localIndexProvider);
              },
              icon: const Icon(Icons.sync),
              label: const Text('Scan selected'),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: FilledButton.tonalIcon(
              onPressed: () async {
                await ref.read(localMediaRepositoryProvider).uploadPending();
                ref.invalidate(localIndexProvider);
              },
              icon: const Icon(Icons.cloud_upload_outlined),
              label: const Text('Upload new media'),
            ),
          ),
          Consumer(
            builder: (context, ref, _) => AsyncStateWidget(
              value: ref.watch(localIndexProvider),
              data: (items) => Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  '${items.length} indexed local items',
                  style: const TextStyle(color: Colors.white70),
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
