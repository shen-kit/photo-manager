import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../application/taxonomy_controller.dart';

class TagsPage extends ConsumerWidget {
  const TagsPage({super.key, this.onSelected});
  final ValueChanged<TagNode>? onSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tags = ref.watch(tagsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tags'),
        actions: [
          IconButton(
            onPressed: () => _create(context, ref),
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: AsyncStateWidget<List<TagNode>>(
        value: tags,
        isEmpty: (items) => items.isEmpty,
        empty: const EmptyState(message: 'No tags yet'),
        onRetry: () => ref.invalidate(tagsProvider),
        data: (items) => ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, index) {
            final depth = '.'.allMatches(items[index].path).length;
            return ListTile(
              contentPadding: EdgeInsets.only(left: 16 + depth * 18, right: 12),
              leading: const Icon(Icons.sell_outlined),
              title: Text(items[index].name),
              subtitle: Text(items[index].path),
              onTap: () =>
                  onSelected == null ? null : onSelected!(items[index]),
            );
          },
        ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create tag'),
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
        .create(album: false, name: name.trim());
    ref.invalidate(tagsProvider);
  }
}
