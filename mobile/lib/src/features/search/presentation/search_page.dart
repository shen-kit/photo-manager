import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/models.dart' hide TrashPage;
import '../../../shared/providers.dart';
import '../../../shared/widgets/async_state_widget.dart';
import '../../assets/data/assets_repository.dart';
import '../../assets/presentation/photo_grid.dart';
import '../../backup/presentation/device_folders_page.dart';
import '../../jobs/presentation/jobs_page.dart';
import '../../notifications/presentation/notifications_page.dart';
import '../../people/presentation/people_page.dart';
import '../../tags/presentation/tags_page.dart';
import '../../trash/presentation/trash_page.dart';
import '../application/search_controller.dart';

class SearchPage extends ConsumerStatefulWidget {
  const SearchPage({super.key});

  @override
  ConsumerState<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends ConsumerState<SearchPage> {
  final _query = TextEditingController();
  final _tagIds = <int>[];
  final _personIds = <String>[];

  @override
  Widget build(BuildContext context) {
    final results = ref.watch(searchControllerProvider);
    final active =
        _query.text.trim().isNotEmpty ||
        _tagIds.isNotEmpty ||
        _personIds.isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: const Text('Search')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _query,
              decoration: InputDecoration(
                prefixIcon: const Icon(Icons.search),
                hintText: 'Search people, places, things',
                suffixIcon: IconButton(
                  onPressed: _openTags,
                  icon: const Icon(Icons.sell_outlined),
                ),
              ),
              onChanged: (_) => _update(),
            ),
          ),
          Expanded(
            child: active
                ? AsyncStateWidget<List<AssetGridItem>>(
                    value: results,
                    isEmpty: (items) => items.isEmpty,
                    empty: const EmptyState(message: 'No matching assets'),
                    data: (items) => TimelineGrid(
                      state: PagedAssetsState(
                        items: items,
                        hasMore: ref
                            .read(searchControllerProvider.notifier)
                            .hasMore,
                      ),
                      onLoadMore: () =>
                          ref.read(searchControllerProvider.notifier).search(),
                    ),
                  )
                : SearchHub(
                    recent: ref.watch(appSettingsProvider).recentSearches,
                    onRecent: (value) {
                      _query.text = value;
                      _update();
                    },
                  ),
          ),
        ],
      ),
    );
  }

  void _update() => ref
      .read(searchControllerProvider.notifier)
      .update(
        SearchStateData(
          query: _query.text,
          personIds: _personIds,
          tagIds: _tagIds,
        ),
      );

  Future<void> _openTags() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => TagsPage(
          onSelected: (tag) {
            if (!_tagIds.contains(tag.id)) _tagIds.add(tag.id);
            Navigator.pop(context);
            _update();
          },
        ),
      ),
    );
  }
}

class SearchHub extends StatelessWidget {
  const SearchHub({super.key, required this.recent, required this.onRecent});
  final List<String> recent;
  final ValueChanged<String> onRecent;

  @override
  Widget build(BuildContext context) {
    final entries = [
      _HubEntry(
        'People',
        Icons.people_outline,
        () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const PeoplePage()),
        ),
      ),
      _HubEntry(
        'Deleted photos',
        Icons.delete_outline,
        () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const TrashPage()),
        ),
      ),
      _HubEntry(
        'Device folders',
        Icons.folder_outlined,
        () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const DeviceFoldersPage()),
        ),
      ),
      _HubEntry(
        'Jobs',
        Icons.work_outline,
        () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const JobsPage()),
        ),
      ),
      _HubEntry(
        'Notifications',
        Icons.notifications_outlined,
        () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const NotificationsPage()),
        ),
      ),
    ];
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: entries.map((e) => _HubCard(entry: e)).toList(),
        ),
        if (recent.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text(
            'Recent searches',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          ...recent.map(
            (q) => ListTile(
              leading: const Icon(Icons.history),
              title: Text(q),
              onTap: () => onRecent(q),
            ),
          ),
        ],
      ],
    );
  }
}

class _HubEntry {
  _HubEntry(this.title, this.icon, this.onTap);
  final String title;
  final IconData icon;
  final VoidCallback onTap;
}

class _HubCard extends StatelessWidget {
  const _HubCard({required this.entry});
  final _HubEntry entry;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: (MediaQuery.sizeOf(context).width - 36) / 2,
    child: Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: entry.onTap,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(entry.icon),
              const SizedBox(height: 16),
              Text(entry.title),
            ],
          ),
        ),
      ),
    ),
  );
}
