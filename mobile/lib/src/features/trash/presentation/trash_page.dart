import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers.dart';
import '../../../shared/widgets/app_image.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../../../shared/widgets/confirm_dialog.dart';
import '../application/trash_providers.dart';

class TrashPage extends ConsumerWidget {
  const TrashPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('Trash'),
      actions: [
        IconButton(
          onPressed: () => _empty(context, ref),
          icon: const Icon(Icons.delete_forever),
        ),
      ],
    ),
    body: AsyncStateWidget(
      value: ref.watch(trashProvider),
      isEmpty: (page) => page.items.isEmpty,
      empty: const EmptyState(message: 'Trash is empty'),
      onRetry: () => ref.invalidate(trashProvider),
      data: (page) => GridView.builder(
        padding: const EdgeInsets.all(4),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          mainAxisSpacing: 2,
          crossAxisSpacing: 2,
        ),
        itemCount: page.items.length,
        itemBuilder: (context, index) => GestureDetector(
          onLongPress: () => _actions(context, ref, page.items[index].id),
          child: AppImage.network(
            ref
                .watch(apiClientProvider)
                .mediaUri(page.items[index].smallThumbnailUrl)
                .toString(),
          ),
        ),
      ),
    ),
  );

  Future<void> _actions(BuildContext context, WidgetRef ref, String id) =>
      showModalBottomSheet(
        context: context,
        builder: (context) => SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.restore),
                title: const Text('Restore'),
                onTap: () async {
                  Navigator.pop(context);
                  await ref.read(trashRepositoryProvider).restore(id);
                  ref.invalidate(trashProvider);
                },
              ),
              ListTile(
                leading: const Icon(Icons.delete_forever),
                title: const Text('Permanently delete'),
                onTap: () async {
                  Navigator.pop(context);
                  if (await confirmDestructive(
                    context,
                    title: 'Permanently delete?',
                    message:
                        'This deletes the original file and cannot be undone.',
                    action: 'Delete',
                  )) {
                    await ref.read(trashRepositoryProvider).deletePermanent(id);
                    ref.invalidate(trashProvider);
                  }
                },
              ),
            ],
          ),
        ),
      );

  Future<void> _empty(BuildContext context, WidgetRef ref) async {
    if (await confirmDestructive(
      context,
      title: 'Empty trash?',
      message: 'This permanently deletes all trashed originals.',
      action: 'Empty',
    )) {
      await ref.read(trashRepositoryProvider).empty();
      ref.invalidate(trashProvider);
    }
  }
}
