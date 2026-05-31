import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers.dart';
import '../../../shared/widgets/app_image.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../../assets/application/assets_controller.dart';
import '../../assets/data/assets_repository.dart';
import '../../assets/presentation/photo_grid.dart';
import '../application/people_providers.dart';

class PeoplePage extends ConsumerWidget {
  const PeoplePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('People')),
    body: AsyncStateWidget(
      value: ref.watch(peopleProvider),
      isEmpty: (items) => items.isEmpty,
      empty: const EmptyState(message: 'No people detected yet'),
      onRetry: () => ref.invalidate(peopleProvider),
      data: (people) => GridView.builder(
        padding: const EdgeInsets.all(12),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          childAspectRatio: .85,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
        ),
        itemCount: people.length,
        itemBuilder: (context, index) => InkWell(
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => PersonDetailPage(
                personId: people[index].id,
                title: people[index].name ?? 'Unnamed person',
              ),
            ),
          ),
          child: Card(
            clipBehavior: Clip.antiAlias,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: people[index].thumbnailUrl == null
                      ? const Icon(Icons.person, size: 64)
                      : AppImage.network(
                          ref
                              .watch(apiClientProvider)
                              .mediaUri(people[index].thumbnailUrl!)
                              .toString(),
                        ),
                ),
                ListTile(
                  title: Text(people[index].name ?? 'Unnamed'),
                  subtitle: Text('${people[index].assetCount} assets'),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class PersonDetailPage extends ConsumerWidget {
  const PersonDetailPage({
    super.key,
    required this.personId,
    required this.title,
  });
  final String personId;
  final String title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = AssetFilter(personIds: [personId]);
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            onPressed: () => _rename(context, ref),
            icon: const Icon(Icons.edit),
          ),
        ],
      ),
      body: FutureBuilder(
        future: ref.watch(assetsRepositoryProvider).firstPage(filter),
        builder: (context, snapshot) {
          if (snapshot.hasError)
            return ErrorState(message: snapshot.error.toString());
          if (!snapshot.hasData)
            return const Center(child: CircularProgressIndicator());
          return TimelineGrid(
            state: snapshot.data!,
            onLoadMore: () =>
                ref.watch(assetsRepositoryProvider).nextPage(filter),
          );
        },
      ),
    );
  }

  Future<void> _rename(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController(
      text: title == 'Unnamed person' ? '' : title,
    );
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename person'),
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
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (value == null) return;
    await ref
        .read(peopleRepositoryProvider)
        .update(personId, name: value.trim());
    ref.invalidate(peopleProvider);
  }
}
